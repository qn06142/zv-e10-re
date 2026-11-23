/* GUI trigger for a returning Linux-user-space RAM payload. No kernel takeover. */
extern unsigned load_payload(unsigned result[2]);
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
/* Direction-only demo. Return bit0=redraw, bit1=consume. */
unsigned process_event(struct state *s, unsigned event) {
    static const unsigned char sequence[4]={5,6,8,7};
    unsigned group=event>>16,key=(event>>4)&15,kind=event&15,old=s->phase,bit;
    if((group!=0x1501 && group!=0x1502) || (event&0xff00) || key<4 || key>8)
        return 0; /* Do not let unrelated notifications erase progress. */
    if(key==4) { /* Center retains Sony's exit behavior. */
        if(kind==2) {s->phase=s->held=0;return 1;}
        return 0;
    }
    bit=1u<<key;s->event=event;++s->count;
    if(kind==1) {s->held&=~bit;return 3;}
    if(kind==4) {s->held|=bit;return 3;}
    if(kind!=2) return 0;
    if(s->held&bit) return 3;
    /* Switching keys replaces a missing release for the previous key. */
    s->held=bit;
    if(old==4) {
        if(key==5) {
            unsigned status=load_payload(s->reserved);
            if(status) {s->reserved[0]=status;s->phase=5;}
            else s->phase=6;
        } else s->phase=0;
        return 3;
    }
    if(old>=5) {s->phase=(key==5)?1:0;return 3;}
    if(key==sequence[old]) s->phase=old+1;
    else s->phase=(key==5)?1:0;
    return 3;
}
unsigned format_keys(char *dst,unsigned capacity,const struct state *s) {
    static const char idle[9]="UP FIRST",confirm[9]="UP=YES? ",error[9]="ERR:0000";
    static const char hex[]="0123456789ABCDEF";
    unsigned i;const char *message=idle;
    if(s->phase==4) message=confirm;
    if(s->phase==5) message=error;
    if(s->phase==6) message=(const char*)s->reserved;
    for(i=0;i<8 && i+1<capacity;++i) {
        char value=message[i];
        if(s->phase==5 && i>=4)value=hex[(s->reserved[0]>>((7-i)*4))&15];
        if(s->phase>0 && s->phase<4) {
            if(i==0) value=(char)('0'+s->phase);
            else if(i==1) value=(s->phase==1)?'D':(s->phase==2)?'L':'R';
            else if(i==2) value=' ';
            else value=hex[(s->event>>((7-i)*4))&15];
        }
        dst[i]=value;
    }
    if(capacity) dst[i]=0;
    return 8;
}
