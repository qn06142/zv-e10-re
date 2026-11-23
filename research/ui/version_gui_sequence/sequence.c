/* GUI-only arming demonstration. No payload, file I/O or kernel handoff. */
struct state { unsigned self, event, count, phase, original_exit, held, reserved[2], vtable[100]; };
unsigned init_state(unsigned *object, struct state *s, unsigned exit_hook) {
    unsigned i, *original = (unsigned *)object[0];
    s->self=(unsigned)object; s->event=s->count=s->phase=s->held=0;
    s->reserved[0]=s->reserved[1]=0;
    s->original_exit=original[1];
    for(i=0;i<100;++i) s->vtable[i]=original[(int)i-2];
    s->vtable[3]=exit_hook;
    object[0]=(unsigned)&s->vtable[2];
    return (unsigned)object;
}
void reset_state(struct state *s) { s->event=s->count=s->phase=s->held=0; }
/* Return bit0=redraw, bit1=consume. Only fresh local key-down advances. */
unsigned process_event(struct state *s, unsigned event) {
    static const unsigned char sequence[5]={5,6,5,6,4};
    unsigned key=(event>>4)&15, kind=event&15, old=s->phase, bit;
    if((event&0xffff0000)!=0x15010000 || (event&0xff00) || key<4 || key>8) {
        if((event>>24)==0x15 && old) { s->phase=0; s->held=0; return 1; }
        return 0;
    }
    bit=1u<<key; s->event=event; ++s->count;
    if(kind==1) { s->held&=~bit; return 1; }
    if(kind==4) { s->held|=bit; return 1|(old?2:0); }
    if(kind!=2) return 0;
    if(s->held&bit) return 1|(old?2:0);
    s->held|=bit;
    if(old==5) { s->phase=(key==4)?6:0; return 3; }
    if(old==6) { s->phase=0; return 3; }
    if(key==sequence[old]) { s->phase=old+1; return 3; }
    s->phase=(key==5)?1:0;
    return 1|((old || key==5)?2:0);
}
unsigned format_keys(char *dst,unsigned capacity,const struct state *s) {
    static const char idle[9]="GUI IDLE", confirm[9]="CONFIRM?", armed[9]="ARMED OK";
    unsigned i; const char *message=idle;
    if(s->phase==5) message=confirm;
    if(s->phase==6) message=armed;
    for(i=0;i<8 && i+1<capacity;++i) {
        char value=message[i];
        if(s->phase>0 && s->phase<5) {
            static const char progress[9]="SEQ 0/5 ";
            value=(i==4)?(char)('0'+s->phase):progress[i];
        }
        dst[i]=value;
    }
    if(capacity) dst[i]=0;
    return 8;
}
