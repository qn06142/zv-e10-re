#ifndef RAW_SNAPSHOT_H
#define RAW_SNAPSHOT_H
#include "raw_live_source.h"
#define SNAP_MAX (4u*1024u*1024u)
#define SNAP_PACKET 614400u
#define SNAP_HEADER 64u
#define SNAP_PAYLOAD (SNAP_PACKET-SNAP_HEADER)
typedef struct {
 unsigned char *data;
 uint32_t bytes,offset,id,sequence,physical;
 int copied,ready;
} raw_snapshot;
/* Serialized worker only. Ready data owns no native references. */
int raw_snapshot_step(raw_snapshot *,raw_live_source *,uint32_t,size_t);
int raw_snapshot_packet(raw_snapshot *,void *);
void raw_snapshot_commit(raw_snapshot *);
void raw_snapshot_reset(raw_snapshot *);
#endif
