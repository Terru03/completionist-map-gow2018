#pragma once

#include <array>
#include <cstdint>
#include <span>
#include <string>
#include <vector>

namespace completionist {

struct StagedRecordInput {
  std::string name;
  std::uint32_t expected_lua_length = 0;
  std::vector<std::uint8_t> envelope;
};

struct DecodedRavenSnapshot {
  bool accepted = false;
  std::array<bool, 53> killed{};
  std::uint32_t alive_count = 0;
  std::uint32_t killed_count = 0;
  std::uint32_t explicit_count = 0;
  std::uint32_t absence_default_false_count = 0;
  std::string reason;
};

DecodedRavenSnapshot DecodeRavenSnapshot(
    std::span<const StagedRecordInput> records);

}  // namespace completionist
