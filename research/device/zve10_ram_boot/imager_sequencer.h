/* SPDX-License-Identifier: GPL-2.0 */
#ifndef ZV_IMAGER_SEQUENCER_H
#define ZV_IMAGER_SEQUENCER_H
#include <stdint.h>

/* IMX284 constructor selects native sequencer index 1. These operations port
 * its verified register accessors; they do not supply power/link/mode setup. */
void imager_seq_configure(uint32_t config0, uint32_t config1);
int imager_seq_upload(const uint8_t *bytes, uint32_t count);
int imager_seq_run(uint32_t mode);
void imager_seq_stop(void);
void imager_seq_ack(void);
void imager_seq_irq_enable(uint32_t enable);
/* Call only for a real DFE IRQ 132. Return -1 for another DFE source so the
 * caller can mask/report it. A zero priority word alone is not completion. */
int imager_seq_handle_irq(void);
#endif
