#pragma once

#include <array>
#include <cstdint>
#include <span>
#include <string>
#include <string_view>
#include <vector>

namespace completionist {

struct StagedRecordInput {
  std::string name;
  std::uint32_t expected_lua_length = 0;
  std::vector<std::uint8_t> envelope;
};

struct NumericStateIdentity {
  std::string_view catalogue_id;
  std::string_view wad;
  std::uint64_t registry_hash;
  std::uint64_t object_hash;
};

struct DecodedNumericStateSnapshot {
  bool accepted = false;
  // Zero means no exact saved state; positive values are stock script enums.
  std::vector<std::uint8_t> states;
  std::string reason;
};

DecodedNumericStateSnapshot DecodeNumericStateSnapshot(
    std::span<const StagedRecordInput> records,
    std::span<const NumericStateIdentity> identities,
    std::uint8_t maximum_state);

struct DecodedRavenSnapshot {
  bool accepted = false;
  std::array<bool, 53> killed{};
  std::array<bool, 53> known{};
  std::array<bool, 53> explicit_state{};
  std::uint32_t alive_count = 0;
  std::uint32_t killed_count = 0;
  std::uint32_t explicit_count = 0;
  std::uint32_t absence_default_false_count = 0;
  std::uint32_t unknown_count = 53;
  std::string reason;
};

DecodedRavenSnapshot DecodeRavenSnapshot(
    std::span<const StagedRecordInput> records);

}  // namespace completionist
