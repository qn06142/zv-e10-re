#ifndef YC_PORT_H
#define YC_PORT_H
#include <stdint.h>
typedef void (*yc_port_log)(const char *,unsigned,unsigned,unsigned);
typedef struct {uint32_t type,offset;uint16_t sds,pad;} yc_port_frame;
int yc_port_init(void *dmm_ctor,void *wire_send,yc_port_log);
/* 0: owned producer transfer, 1: pending/control, 2: closed, -1: uncertainty. */
int yc_port_next(yc_port_frame *,unsigned timeout);
int yc_port_complete(void);
int yc_port_close(void);
int yc_port_is_closed(void);
#endif
