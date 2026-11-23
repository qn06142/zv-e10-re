#include "payload.h"
#ifndef PAYLOAD_TEXT
#define PAYLOAD_TEXT "HELLO"
#endif
unsigned payload_entry(struct ram_api *api) {
    static const char text[]=PAYLOAD_TEXT;
    unsigned i;
    if(!api || api->version!=RAM_ABI || api->size!=sizeof(*api) || api->capacity<sizeof(text))
        return 0;
    for(i=0;i<sizeof(text);++i) api->text[i]=text[i];
    return RAM_RETURN;
}
