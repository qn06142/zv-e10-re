#ifndef ZV_RAM_PAYLOAD_H
#define ZV_RAM_PAYLOAD_H
#define RAM_ABI 1u
#define RAM_RETURN 0x52414d31u
struct ram_api { unsigned version, size; char *text; unsigned capacity; };
#endif
