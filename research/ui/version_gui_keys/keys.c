/* Display-only event probe: no I/O, allocation, loading or OS handoff. */
struct key_state { unsigned self, event, count, reserved; };
unsigned format_keys(char *dst, unsigned capacity, const struct key_state *state) {
    static const char idle[] = "GUI KEYS";
    static const char hex[] = "0123456789ABCDEF";
    unsigned i, event = state->event;
    for (i = 0; i != 8 && i + 1 < capacity; ++i) {
        if (!event) dst[i] = idle[i];
        else if (i == 0) dst[i] = 'E';
        else if (i == 1) dst[i] = ':';
        else dst[i] = hex[(event >> ((7 - i) * 4)) & 15];
    }
    if (capacity) dst[i] = 0;
    return 8;
}
