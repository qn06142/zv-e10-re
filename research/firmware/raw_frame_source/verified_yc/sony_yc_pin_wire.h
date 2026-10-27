/* Recovered from actual dataflowInfraFramework.so constructors and Pin::Send/SendComp.
 * Wire-only helpers: no queue creation, subscription or ownership guarantee. */
#ifndef SONY_YC_PIN_WIRE_H
#define SONY_YC_PIN_WIRE_H
#include <stdint.h>
#include <stddef.h>
#define SONY_PIN_SEND_BYTES 0x34u
#define SONY_PIN_COMPLETE_BYTES 0x2cu
#define SONY_VDF_QUEUE_VERIFIED 0x0059000eu
typedef struct { uint32_t data_type, direction, index, queue; } sony_pin_property;
typedef struct {
 sony_pin_property output, input;
 uint32_t tag, auxiliary;
 uint16_t metadata_unit;
} sony_pin_frame_send;
/* Decode native category0x1000 / SEND0x0102, version1. All enums remain native.
 * Output/input properties retain their logical producer/consumer order in ACK. */
int sony_pin_decode_send(const void *,size_t,sony_pin_frame_send *);
int sony_pin_make_complete(const sony_pin_frame_send *,int32_t,void *,size_t);
#endif
