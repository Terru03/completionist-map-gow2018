typedef unsigned char u8;
typedef int i32;

typedef struct TValue {
    union { void *gc; void *p; i32 b; void *f; } value_;
    i32 tt_;
    i32 _pad;
} TValue;

typedef struct lua_State_min {
    void *next;
    u8 tt;
    u8 marked;
    u8 status;
    u8 _pad0[5];
    TValue *top;
} lua_State_min;

static __forceinline void push_bool(lua_State_min *L, int value) {
    TValue *slot = L->top;
    slot->value_.b = value ? 1 : 0;
    slot->tt_ = 1;
    L->top = slot + 1;
}

static int emit(lua_State_min *L, int chunk) {
    int count = chunk < 2 ? 18 : 17;
    push_bool(L, 1);
    for (int i = 0; i < count; ++i) {
        push_bool(L, ((chunk * 18 + i) & 1) == 0);
    }
    return count + 1;
}

__declspec(dllexport) int completionist_raven_probe_a(lua_State_min *L) { return emit(L, 0); }
__declspec(dllexport) int completionist_raven_probe_b(lua_State_min *L) { return emit(L, 1); }
__declspec(dllexport) int completionist_raven_probe_c(lua_State_min *L) { return emit(L, 2); }

__declspec(dllexport) int DllMain(void *module, unsigned long reason, void *reserved) {
    (void)module; (void)reason; (void)reserved;
    return 1;
}
