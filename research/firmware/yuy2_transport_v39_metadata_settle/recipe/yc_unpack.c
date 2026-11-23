#include "yc_unpack.h"
void yc_uyvy_to_yuy2(unsigned char *out,const unsigned char *in,unsigned n){
 for(unsigned i=0;i+3<n;i+=4){unsigned u=in[i],y0=in[i+1],v=in[i+2],y1=in[i+3];out[i]=y0;out[i+1]=u;out[i+2]=y1;out[i+3]=v;}
}
