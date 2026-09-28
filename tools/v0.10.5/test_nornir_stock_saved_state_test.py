"""Check that checkpoint state changes only stock Nornir Lua."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

from lupa.lua51 import LuaRuntime

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "nornir_stock_saved_builder_test", HERE / "build-nornir-stock-saved-state-test.py")
assert spec is not None and spec.loader is not None
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class StockSavedCandidateTest(unittest.TestCase):
    def test_only_map_lua_changes_and_lua51_compiles(self):
        source = (HERE.parents[1] /
                  "build/nornir-native-material-key-isolated-test/source-game-root")
        outputs, report = builder.build(source)
        old = json.loads(builder.stock.REPORT.read_text(encoding="utf-8"))
        changed = [name for name in outputs
                   if old["files"][name]["sha256"] != report["files"][name]["sha256"]]
        self.assertEqual(changed, [builder.MAP])
        self.assertEqual(report["required_native_bridge_sha256"], builder.BRIDGE_SHA256)
        self.assertEqual(report["untouched_sha256"], old["untouched_sha256"])
        self.assertTrue(outputs[builder.MAP].startswith(
            builder.stock.handoff.inject((source / builder.MAP).read_bytes())))
        self.assertEqual(hashlib.sha256(outputs[builder.MAP]).hexdigest(),
                         report["files"][builder.MAP]["sha256"])
        self.assertEqual(outputs[builder.MAP], (builder.OUT / builder.MAP).read_bytes())
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.globals().source = outputs[builder.MAP].decode("utf-8-sig")
        lua.execute("assert(loadstring(source))")

    def test_reply_rejects_wrong_epoch_nonce_or_contract(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.globals().source = builder.READER.read_text(encoding="utf-8")
        lua.execute("""
          local Saved = assert(loadstring(source))()
          local contract = string.rep('a', 64)
          local rows = {{family='nornir_chest', id='b'},
                        {family='nornir_chest', id='a'}}
          local transport = {now=function() return 10 end,
                             create=function() error('not used') end}
          local reader = Saved.New(rows, contract, transport, function() return 7 end)
          reader:Reset(3)
          reader.nonce = 5
          local response = 'NORNIR_SNAPSHOT_V1 nonce=5 restoreEpoch=7 contract='..
                           contract..' states=41'
          local parsed = reader:Parse(response)
          assert(parsed and parsed.states.a == 4 and parsed.states.b == 1)
          assert(reader:Parse(string.gsub(response, 'nonce=5', 'nonce=6')) == nil)
          assert(reader:Parse(string.gsub(response, 'restoreEpoch=7', 'restoreEpoch=8')) == nil)
          assert(reader:Parse(string.gsub(response, contract, string.rep('b',64))) == nil)
          reader.snapshot = parsed
          reader.snapshotTime = 10
          assert(reader:Current(3) == parsed and reader:Current(4) == nil)
          reader:Reset(4)
          assert(reader:Current(4) == nil)
        """)


if __name__ == "__main__":
    unittest.main()
