#pragma once

#include <array>
#include <cstdint>
#include <string>

namespace completionist {

using Sha256 = std::array<std::uint8_t, 32>;

bool Sha256File(const std::wstring& path, Sha256* digest, std::string* reason);
std::string Sha256Hex(const Sha256& digest);
bool IsSupportedExecutableHash(const Sha256& digest);

}  // namespace completionist
