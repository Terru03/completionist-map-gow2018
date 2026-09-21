import sys
sys.argv=['inspect_restore.py','schema']
exec(open('.research-index/inspect_restore.py').read().split("mode=sys.argv[1]")[0])
fns=set(r[0] for r in con.execute('select distinct src_fn from rip_refs where target between ? and ?', (0x22c7170,0x22c7217)))
for a in sorted(fns):
 f=base.fn_for(con,a)
 if not f: continue
 hits=[]
 for i in md.disasm(pe.read(a,f['end']-a),pe.image_base+a):
  if any(op.type==3 and i.reg_name(op.mem.base) not in ['rip','rsp','rbp'] and op.mem.disp in [0x60,0x64,0x68,0x6c,0x70,0x74,0x78,0x7c,0x80,0xa0,0xa4] for op in i.operands):
   hits.append(f'{i.address-pe.image_base:08X} {i.mnemonic} {i.op_str}')
 if hits: print(hex(a),'\n'+'\n'.join(hits))
