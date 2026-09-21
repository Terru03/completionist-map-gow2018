#include <windows.h>
#include <psapi.h>

#include <algorithm>
#include <cctype>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace {

struct ImportSlot {
  std::uint32_t iat_rva = 0;
  std::optional<std::uint16_t> ordinal;
  std::string name;
};

struct ProcessBasicInformationLocal {
  void* reserved1;
  void* peb_base_address;
  void* reserved2[2];
  ULONG_PTR unique_process_id;
  void* reserved3;
};

struct RemoteListEntry64 {
  std::uint64_t flink;
  std::uint64_t blink;
};

struct RemoteUnicodeString64 {
  std::uint16_t length;
  std::uint16_t maximum_length;
  std::uint32_t padding;
  std::uint64_t buffer;
};

using NtQueryInformationProcessFn =
    LONG(NTAPI*)(HANDLE, ULONG, void*, ULONG, ULONG*);

constexpr std::uintptr_t kPebImageBaseOffset = 0x10;
constexpr std::uintptr_t kPebLdrOffset = 0x18;
constexpr std::uintptr_t kLdrInLoadOrderListOffset = 0x10;
constexpr std::uintptr_t kLdrEntryDllBaseOffset = 0x30;
constexpr std::uintptr_t kLdrEntrySizeOfImageOffset = 0x40;
constexpr std::uintptr_t kLdrEntryFullDllNameOffset = 0x48;
constexpr std::size_t kMaxRemoteModules = 512;

std::string LowerAscii(std::string value) {
  std::transform(value.begin(), value.end(), value.begin(),
                 [](unsigned char ch) {
                   return static_cast<char>(std::tolower(ch));
                 });
  return value;
}

bool EqualsIgnoreCaseAscii(std::string_view left, std::string_view right) {
  if (left.size() != right.size()) {
    return false;
  }
  for (std::size_t i = 0; i < left.size(); ++i) {
    const auto a =
        static_cast<unsigned char>(left[i]);
    const auto b =
        static_cast<unsigned char>(right[i]);
    if (std::tolower(a) != std::tolower(b)) {
      return false;
    }
  }
  return true;
}

std::string Win32ErrorText(DWORD error) {
  char* buffer = nullptr;
  const DWORD length = FormatMessageA(
      FORMAT_MESSAGE_ALLOCATE_BUFFER | FORMAT_MESSAGE_FROM_SYSTEM |
          FORMAT_MESSAGE_IGNORE_INSERTS,
      nullptr, error, 0, reinterpret_cast<char*>(&buffer), 0, nullptr);
  std::string result;
  if (length != 0 && buffer != nullptr) {
    result.assign(buffer, length);
    while (!result.empty() &&
           (result.back() == '\r' || result.back() == '\n')) {
      result.pop_back();
    }
  } else {
    result = "unknown Win32 error";
  }
  if (buffer != nullptr) {
    LocalFree(buffer);
  }
  return result;
}

std::wstring Utf8ToWide(const std::string& input) {
  if (input.empty()) {
    return {};
  }
  const int needed = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS,
                                         input.data(),
                                         static_cast<int>(input.size()),
                                         nullptr, 0);
  if (needed <= 0) {
    throw std::runtime_error("invalid UTF-8 argument");
  }
  std::wstring output(static_cast<std::size_t>(needed), L'\0');
  if (MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, input.data(),
                          static_cast<int>(input.size()), output.data(),
                          needed) != needed) {
    throw std::runtime_error("UTF-8 conversion failed");
  }
  return output;
}

std::string WideToUtf8(const std::wstring& input) {
  if (input.empty()) {
    return {};
  }
  const int needed = WideCharToMultiByte(CP_UTF8, 0, input.data(),
                                         static_cast<int>(input.size()),
                                         nullptr, 0, nullptr, nullptr);
  if (needed <= 0) {
    return {};
  }
  std::string output(static_cast<std::size_t>(needed), '\0');
  if (WideCharToMultiByte(CP_UTF8, 0, input.data(),
                          static_cast<int>(input.size()), output.data(),
                          needed, nullptr, nullptr) != needed) {
    return {};
  }
  return output;
}

std::vector<std::uint8_t> ReadWholeFile(const std::wstring& path) {
  std::ifstream stream(std::filesystem::path(path), std::ios::binary);
  if (!stream) {
    throw std::runtime_error("could not open PE file");
  }
  stream.seekg(0, std::ios::end);
  const std::streamoff size = stream.tellg();
  if (size <= 0) {
    throw std::runtime_error("PE file is empty");
  }
  stream.seekg(0, std::ios::beg);
  std::vector<std::uint8_t> bytes(static_cast<std::size_t>(size));
  stream.read(reinterpret_cast<char*>(bytes.data()), size);
  if (!stream) {
    throw std::runtime_error("failed reading PE file");
  }
  return bytes;
}

template <typename T>
const T* FileObjectAt(const std::vector<std::uint8_t>& bytes,
                      std::size_t offset) {
  if (offset > bytes.size() || sizeof(T) > bytes.size() - offset) {
    return nullptr;
  }
  return reinterpret_cast<const T*>(bytes.data() + offset);
}

std::optional<std::size_t> RvaToFileOffset(
    const std::vector<std::uint8_t>& bytes,
    const IMAGE_NT_HEADERS64& nt,
    const IMAGE_SECTION_HEADER* sections,
    std::uint32_t rva) {
  if (rva < nt.OptionalHeader.SizeOfHeaders) {
    if (rva < bytes.size()) {
      return static_cast<std::size_t>(rva);
    }
    return std::nullopt;
  }

  for (WORD i = 0; i < nt.FileHeader.NumberOfSections; ++i) {
    const auto& section = sections[i];
    const std::uint32_t span =
        std::max(section.Misc.VirtualSize, section.SizeOfRawData);
    if (rva >= section.VirtualAddress &&
        static_cast<std::uint64_t>(rva) <
            static_cast<std::uint64_t>(section.VirtualAddress) + span) {
      const std::uint64_t offset =
          static_cast<std::uint64_t>(section.PointerToRawData) +
          (rva - section.VirtualAddress);
      if (offset < bytes.size()) {
        return static_cast<std::size_t>(offset);
      }
      return std::nullopt;
    }
  }
  return std::nullopt;
}

std::optional<std::string> ReadAsciiStringRva(
    const std::vector<std::uint8_t>& bytes,
    const IMAGE_NT_HEADERS64& nt,
    const IMAGE_SECTION_HEADER* sections,
    std::uint32_t rva) {
  const auto offset = RvaToFileOffset(bytes, nt, sections, rva);
  if (!offset.has_value()) {
    return std::nullopt;
  }
  std::string value;
  for (std::size_t i = *offset; i < bytes.size(); ++i) {
    const char ch = static_cast<char>(bytes[i]);
    if (ch == '\0') {
      return value;
    }
    value.push_back(ch);
    if (value.size() > 4096) {
      return std::nullopt;
    }
  }
  return std::nullopt;
}

std::vector<ImportSlot> FindImports(const std::wstring& exe_path,
                                    const std::string& wanted_dll) {
  const auto bytes = ReadWholeFile(exe_path);
  const auto* dos = FileObjectAt<IMAGE_DOS_HEADER>(bytes, 0);
  if (dos == nullptr || dos->e_magic != IMAGE_DOS_SIGNATURE ||
      dos->e_lfanew <= 0) {
    throw std::runtime_error("invalid DOS header");
  }

  const std::size_t nt_offset = static_cast<std::size_t>(dos->e_lfanew);
  const auto* nt = FileObjectAt<IMAGE_NT_HEADERS64>(bytes, nt_offset);
  if (nt == nullptr || nt->Signature != IMAGE_NT_SIGNATURE ||
      nt->OptionalHeader.Magic != IMAGE_NT_OPTIONAL_HDR64_MAGIC ||
      nt->FileHeader.Machine != IMAGE_FILE_MACHINE_AMD64) {
    throw std::runtime_error("expected AMD64 PE32+ image");
  }

  const std::size_t sections_offset =
      nt_offset + offsetof(IMAGE_NT_HEADERS64, OptionalHeader) +
      nt->FileHeader.SizeOfOptionalHeader;
  const std::uint64_t sections_bytes =
      static_cast<std::uint64_t>(nt->FileHeader.NumberOfSections) *
      sizeof(IMAGE_SECTION_HEADER);
  if (sections_offset > bytes.size() ||
      sections_bytes > bytes.size() - sections_offset) {
    throw std::runtime_error("invalid PE section table");
  }
  const auto* sections = reinterpret_cast<const IMAGE_SECTION_HEADER*>(
      bytes.data() + sections_offset);

  const auto& import_dir =
      nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
  if (import_dir.VirtualAddress == 0) {
    throw std::runtime_error("PE has no normal import directory");
  }
  const auto import_offset =
      RvaToFileOffset(bytes, *nt, sections, import_dir.VirtualAddress);
  if (!import_offset.has_value()) {
    throw std::runtime_error("import directory RVA is not file-backed");
  }

  for (std::size_t index = 0; index < 4096; ++index) {
    const std::size_t descriptor_offset =
        *import_offset + index * sizeof(IMAGE_IMPORT_DESCRIPTOR);
    const auto* descriptor =
        FileObjectAt<IMAGE_IMPORT_DESCRIPTOR>(bytes, descriptor_offset);
    if (descriptor == nullptr) {
      throw std::runtime_error("truncated import descriptor table");
    }
    if (descriptor->Name == 0 && descriptor->FirstThunk == 0 &&
        descriptor->OriginalFirstThunk == 0) {
      break;
    }

    const auto dll_name =
        ReadAsciiStringRva(bytes, *nt, sections, descriptor->Name);
    if (!dll_name.has_value()) {
      throw std::runtime_error("invalid import DLL name");
    }
    if (!EqualsIgnoreCaseAscii(*dll_name, wanted_dll)) {
      continue;
    }

    const std::uint32_t lookup_rva =
        descriptor->OriginalFirstThunk != 0
            ? descriptor->OriginalFirstThunk
            : descriptor->FirstThunk;
    const auto lookup_offset =
        RvaToFileOffset(bytes, *nt, sections, lookup_rva);
    if (!lookup_offset.has_value()) {
      throw std::runtime_error("import lookup table is not file-backed");
    }

    std::vector<ImportSlot> slots;
    for (std::size_t thunk_index = 0; thunk_index < 4096; ++thunk_index) {
      const auto* thunk = FileObjectAt<IMAGE_THUNK_DATA64>(
          bytes, *lookup_offset + thunk_index * sizeof(IMAGE_THUNK_DATA64));
      if (thunk == nullptr) {
        throw std::runtime_error("truncated import lookup table");
      }
      const ULONGLONG value = thunk->u1.AddressOfData;
      if (value == 0) {
        break;
      }

      ImportSlot slot;
      const std::uint64_t iat_rva =
          static_cast<std::uint64_t>(descriptor->FirstThunk) +
          thunk_index * sizeof(std::uint64_t);
      if (iat_rva > UINT32_MAX) {
        throw std::runtime_error("IAT RVA overflow");
      }
      slot.iat_rva = static_cast<std::uint32_t>(iat_rva);

      if (IMAGE_SNAP_BY_ORDINAL64(value)) {
        slot.ordinal = static_cast<std::uint16_t>(IMAGE_ORDINAL64(value));
      } else {
        if (value > UINT32_MAX) {
          throw std::runtime_error("import name RVA overflow");
        }
        const auto name_offset = RvaToFileOffset(
            bytes, *nt, sections, static_cast<std::uint32_t>(value));
        if (!name_offset.has_value() ||
            *name_offset + sizeof(std::uint16_t) >= bytes.size()) {
          throw std::runtime_error("invalid IMAGE_IMPORT_BY_NAME");
        }
        std::string name;
        for (std::size_t pos = *name_offset + sizeof(std::uint16_t);
             pos < bytes.size(); ++pos) {
          const char ch = static_cast<char>(bytes[pos]);
          if (ch == '\0') {
            break;
          }
          name.push_back(ch);
          if (name.size() > 4096) {
            throw std::runtime_error("import name too long");
          }
        }
        slot.name = std::move(name);
      }
      slots.push_back(std::move(slot));
    }

    if (slots.empty()) {
      throw std::runtime_error("matching import descriptor has no entries");
    }
    return slots;
  }

  throw std::runtime_error("requested DLL is not a normal import");
}

template <typename T>
bool ReadRemote(HANDLE process, std::uintptr_t address, T* value,
                DWORD* error) {
  SIZE_T read = 0;
  if (value == nullptr ||
      !ReadProcessMemory(process, reinterpret_cast<const void*>(address),
                         value, sizeof(T), &read) ||
      read != sizeof(T)) {
    if (error != nullptr) {
      *error = GetLastError();
    }
    return false;
  }
  return true;
}

bool ReadRemoteBytes(HANDLE process, std::uintptr_t address, void* buffer,
                     std::size_t size, DWORD* error) {
  SIZE_T read = 0;
  if (buffer == nullptr ||
      !ReadProcessMemory(process, reinterpret_cast<const void*>(address),
                         buffer, size, &read) ||
      read != size) {
    if (error != nullptr) {
      *error = GetLastError();
    }
    return false;
  }
  return true;
}

NtQueryInformationProcessFn ResolveNtQueryInformationProcess() {
  const HMODULE ntdll = GetModuleHandleW(L"ntdll.dll");
  if (ntdll == nullptr) {
    return nullptr;
  }
  return reinterpret_cast<NtQueryInformationProcessFn>(
      GetProcAddress(ntdll, "NtQueryInformationProcess"));
}

bool GetPebAddress(HANDLE process, std::uintptr_t* peb, DWORD* error) {
  if (peb == nullptr) {
    if (error != nullptr) {
      *error = ERROR_INVALID_PARAMETER;
    }
    return false;
  }
  const auto query = ResolveNtQueryInformationProcess();
  if (query == nullptr) {
    if (error != nullptr) {
      *error = ERROR_PROC_NOT_FOUND;
    }
    return false;
  }
  ProcessBasicInformationLocal info{};
  ULONG returned = 0;
  const LONG status =
      query(process, 0, &info, static_cast<ULONG>(sizeof(info)), &returned);
  if (status < 0 || info.peb_base_address == nullptr) {
    if (error != nullptr) {
      *error = ERROR_GEN_FAILURE;
    }
    return false;
  }
  *peb = reinterpret_cast<std::uintptr_t>(info.peb_base_address);
  return true;
}

bool GetRemoteImageBase(HANDLE process, std::uintptr_t peb,
                        std::uintptr_t* image_base, DWORD* error) {
  std::uint64_t value = 0;
  if (!ReadRemote(process, peb + kPebImageBaseOffset, &value, error)) {
    return false;
  }
  if (value == 0) {
    if (error != nullptr) {
      *error = ERROR_INVALID_ADDRESS;
    }
    return false;
  }
  *image_base = static_cast<std::uintptr_t>(value);
  return true;
}

std::optional<std::wstring> ReadRemoteUnicodeString(
    HANDLE process, const RemoteUnicodeString64& remote, DWORD* error) {
  if (remote.length == 0) {
    return std::wstring();
  }
  if (remote.length > remote.maximum_length ||
      (remote.length % sizeof(wchar_t)) != 0 ||
      remote.length > 32766 * sizeof(wchar_t) || remote.buffer == 0) {
    if (error != nullptr) {
      *error = ERROR_INVALID_DATA;
    }
    return std::nullopt;
  }
  std::wstring value(remote.length / sizeof(wchar_t), L'\0');
  if (!ReadRemoteBytes(process, static_cast<std::uintptr_t>(remote.buffer),
                       value.data(), remote.length, error)) {
    return std::nullopt;
  }
  return value;
}

std::optional<std::wstring> FindOwnerThroughPeb(
    HANDLE process, std::uintptr_t peb, std::uintptr_t target,
    DWORD* error) {
  std::uint64_t ldr = 0;
  if (!ReadRemote(process, peb + kPebLdrOffset, &ldr, error) || ldr == 0) {
    return std::nullopt;
  }

  const std::uintptr_t head =
      static_cast<std::uintptr_t>(ldr) + kLdrInLoadOrderListOffset;
  RemoteListEntry64 head_links{};
  if (!ReadRemote(process, head, &head_links, error)) {
    return std::nullopt;
  }

  std::uintptr_t current =
      static_cast<std::uintptr_t>(head_links.flink);
  for (std::size_t count = 0;
       count < kMaxRemoteModules && current != 0 && current != head;
       ++count) {
    std::uint64_t dll_base = 0;
    std::uint32_t image_size = 0;
    RemoteUnicodeString64 full_name{};
    RemoteListEntry64 links{};

    if (!ReadRemote(process, current, &links, error) ||
        !ReadRemote(process, current + kLdrEntryDllBaseOffset,
                    &dll_base, error) ||
        !ReadRemote(process, current + kLdrEntrySizeOfImageOffset,
                    &image_size, error) ||
        !ReadRemote(process, current + kLdrEntryFullDllNameOffset,
                    &full_name, error)) {
      return std::nullopt;
    }

    if (dll_base != 0 && image_size != 0) {
      const std::uint64_t begin = dll_base;
      const std::uint64_t end =
          begin + static_cast<std::uint64_t>(image_size);
      if (end >= begin &&
          static_cast<std::uint64_t>(target) >= begin &&
          static_cast<std::uint64_t>(target) < end) {
        return ReadRemoteUnicodeString(process, full_name, error);
      }
    }

    current = static_cast<std::uintptr_t>(links.flink);
  }

  if (error != nullptr) {
    *error = ERROR_NOT_FOUND;
  }
  return std::nullopt;
}

std::optional<std::wstring> FindOwnerThroughMappedFile(
    HANDLE process, std::uintptr_t target, DWORD* error) {
  std::vector<wchar_t> buffer(32768);
  const DWORD length = GetMappedFileNameW(
      process, reinterpret_cast<void*>(target), buffer.data(),
      static_cast<DWORD>(buffer.size()));
  if (length == 0) {
    if (error != nullptr) {
      *error = GetLastError();
    }
    return std::nullopt;
  }
  return std::wstring(buffer.data(), length);
}

void PrintHexAddress(std::uintptr_t value) {
  std::cout << "0x" << std::hex << std::uppercase
            << static_cast<std::uint64_t>(value)
            << std::dec << std::nouppercase;
}

int SelfTest() {
  HANDLE process = OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ,
                               FALSE, GetCurrentProcessId());
  if (process == nullptr) {
    const DWORD error = GetLastError();
    std::cerr << "RAVEN_IMPORT_PROBE_SELFTEST_FAILED open_process_error="
              << error << " " << Win32ErrorText(error) << "\n";
    return 1;
  }

  std::uintptr_t peb = 0;
  DWORD error = ERROR_SUCCESS;
  if (!GetPebAddress(process, &peb, &error)) {
    CloseHandle(process);
    std::cerr << "RAVEN_IMPORT_PROBE_SELFTEST_FAILED peb_error="
              << error << "\n";
    return 1;
  }

  const HMODULE kernel32 = GetModuleHandleW(L"kernel32.dll");
  const FARPROC function =
      kernel32 != nullptr
          ? GetProcAddress(kernel32, "GetCurrentProcessId")
          : nullptr;
  if (function == nullptr) {
    CloseHandle(process);
    std::cerr << "RAVEN_IMPORT_PROBE_SELFTEST_FAILED local_symbol\n";
    return 1;
  }

  const auto owner = FindOwnerThroughPeb(
      process, peb, reinterpret_cast<std::uintptr_t>(function), &error);
  CloseHandle(process);
  if (!owner.has_value() || owner->empty()) {
    std::cerr << "RAVEN_IMPORT_PROBE_SELFTEST_FAILED owner_error="
              << error << "\n";
    return 1;
  }

  std::cout << "RAVEN_IMPORT_PROBE_SELFTEST_PASSED owner="
            << WideToUtf8(*owner) << "\n";
  return 0;
}

}  // namespace

int wmain(int argc, wchar_t** argv) {
  try {
    if (argc == 2 && std::wstring_view(argv[1]) == L"--self-test") {
      return SelfTest();
    }

    DWORD pid = 0;
    std::wstring exe_path;
    std::string dll_name;
    for (int i = 1; i < argc; ++i) {
      const std::wstring_view arg(argv[i]);
      if (arg == L"--pid" && i + 1 < argc) {
        pid = static_cast<DWORD>(std::stoul(argv[++i]));
      } else if (arg == L"--exe" && i + 1 < argc) {
        exe_path = argv[++i];
      } else if (arg == L"--dll" && i + 1 < argc) {
        dll_name = WideToUtf8(argv[++i]);
      } else {
        std::wcerr << L"Unknown or incomplete argument: " << argv[i] << L"\n";
        return 2;
      }
    }

    if (pid == 0 || exe_path.empty() || dll_name.empty()) {
      std::cerr << "Usage: raven_bridge_import_probe --pid <pid> "
                   "--exe <path> --dll <name>\n";
      return 2;
    }

    const auto imports = FindImports(exe_path, dll_name);
    HANDLE process = OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ,
                                 FALSE, pid);
    if (process == nullptr) {
      const DWORD error = GetLastError();
      std::cerr << "RAVEN_IMPORT_PROBE_FAILED open_process_error="
                << error << " " << Win32ErrorText(error) << "\n";
      return 1;
    }

    std::uintptr_t peb = 0;
    DWORD error = ERROR_SUCCESS;
    if (!GetPebAddress(process, &peb, &error)) {
      CloseHandle(process);
      std::cerr << "RAVEN_IMPORT_PROBE_FAILED peb_error=" << error << "\n";
      return 1;
    }

    std::uintptr_t image_base = 0;
    if (!GetRemoteImageBase(process, peb, &image_base, &error)) {
      CloseHandle(process);
      std::cerr << "RAVEN_IMPORT_PROBE_FAILED image_base_error="
                << error << "\n";
      return 1;
    }

    std::cout << "RAVEN_IMPORT_PROBE_PROCESS pid=" << pid
              << " dll=" << dll_name
              << " slots=" << imports.size()
              << " image_base=";
    PrintHexAddress(image_base);
    std::cout << "\n";

    bool all_resolved = true;
    std::string first_owner;
    bool owner_consistent = true;

    for (const auto& slot : imports) {
      std::uint64_t target_value = 0;
      const std::uintptr_t slot_address =
          image_base + static_cast<std::uintptr_t>(slot.iat_rva);
      if (!ReadRemote(process, slot_address, &target_value, &error) ||
          target_value == 0) {
        std::cout << "RAVEN_IMPORT_SLOT iat_rva=0x"
                  << std::hex << std::uppercase << slot.iat_rva
                  << std::dec << std::nouppercase;
        if (slot.ordinal.has_value()) {
          std::cout << " ordinal=" << *slot.ordinal;
        } else {
          std::cout << " name=" << slot.name;
        }
        std::cout << " target=unreadable error=" << error << "\n";
        all_resolved = false;
        continue;
      }

      const std::uintptr_t target =
          static_cast<std::uintptr_t>(target_value);
      DWORD peb_error = ERROR_SUCCESS;
      auto owner = FindOwnerThroughPeb(process, peb, target, &peb_error);
      std::string method = "peb";
      if (!owner.has_value() || owner->empty()) {
        DWORD mapped_error = ERROR_SUCCESS;
        owner = FindOwnerThroughMappedFile(process, target, &mapped_error);
        method = "mapped_file";
        if (!owner.has_value() || owner->empty()) {
          std::cout << "RAVEN_IMPORT_SLOT iat_rva=0x"
                    << std::hex << std::uppercase << slot.iat_rva
                    << std::dec << std::nouppercase;
          if (slot.ordinal.has_value()) {
            std::cout << " ordinal=" << *slot.ordinal;
          } else {
            std::cout << " name=" << slot.name;
          }
          std::cout << " target=";
          PrintHexAddress(target);
          std::cout << " owner=unresolved peb_error=" << peb_error
                    << " mapped_error=" << mapped_error << "\n";
          all_resolved = false;
          continue;
        }
      }

      const std::string owner_utf8 = WideToUtf8(*owner);
      if (first_owner.empty()) {
        first_owner = LowerAscii(owner_utf8);
      } else if (LowerAscii(owner_utf8) != first_owner) {
        owner_consistent = false;
      }

      std::cout << "RAVEN_IMPORT_SLOT iat_rva=0x"
                << std::hex << std::uppercase << slot.iat_rva
                << std::dec << std::nouppercase;
      if (slot.ordinal.has_value()) {
        std::cout << " ordinal=" << *slot.ordinal;
      } else {
        std::cout << " name=" << slot.name;
      }
      std::cout << " target=";
      PrintHexAddress(target);
      std::cout << " owner_method=" << method
                << " owner=" << owner_utf8 << "\n";
    }

    CloseHandle(process);

    if (!all_resolved) {
      std::cout << "RAVEN_IMPORT_PROBE_INCOMPLETE\n";
      return 1;
    }

    std::cout << "RAVEN_IMPORT_PROBE_COMPLETE dll=" << dll_name
              << " slots=" << imports.size()
              << " owner_consistent="
              << (owner_consistent ? "true" : "false") << "\n";
    return owner_consistent ? 0 : 1;
  } catch (const std::exception& exception) {
    std::cerr << "RAVEN_IMPORT_PROBE_FAILED exception="
              << exception.what() << "\n";
    return 1;
  }
}
