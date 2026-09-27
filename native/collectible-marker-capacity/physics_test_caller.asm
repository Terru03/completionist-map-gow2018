; Reproduce the world-construction call site's RCX/ESI contract while preserving
; the Windows x64 ABI for the C++ test caller.
.code
InvokePhysicsThunk PROC FRAME
    push rsi
    .pushreg rsi
    sub rsp, 20h
    .allocstack 20h
    .endprolog
    mov esi, edx
    call r8
    add rsp, 20h
    pop rsi
    ret
InvokePhysicsThunk ENDP
END
