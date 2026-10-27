#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#define R 400
static char bits[R][193];static unsigned hdr[R],end[R],nr;
static unsigned get(const unsigned char *p){return p[0]|p[1]<<8|p[2]<<16|p[3]<<24;}
static int run(const char*s,unsigned h,int*map,int order,int base,int pol,int sign,int kind){
 int p=16;if(base)p+=base;
 for(int group=0;group<8;group++){
  int q=(h>>((order?7-group:group)*2))&3,k=map[q];
  for(int j=(group==0 && base)?1:0;j<8;j++){
   int z=0;while(p<192 && (s[p]-'0')==pol){z++;p++;}if(p>=192)return -1;p++;
   int n=kind?k+z:k;if(p+n>192 || z>20)return -1;
   int nonzero=z;for(int t=0;t<n;t++)nonzero|=s[p+t]-'0';p+=n;
   if(sign && nonzero)p++;
   if(p>192)return -1;
  }
 }
 return p;
}
int main(int argc,char**argv){if(argc!=2)return 2;FILE*f=fopen(argv[1],"rb");if(!f)return 3;unsigned char b[614400];if(fread(b,1,sizeof(b),f)!=sizeof(b))return 4;fclose(f);int count=0;
 for(int off=0;off<614400 && nr<R;off+=64){int zero=1;for(int i=32;i<48;i++)zero&=b[off+i]==0;if(!zero || count++%9)continue;
  uint64_t w[8];memcpy(w,b+off,64);hdr[nr]=(unsigned)(w[0]>>48);int order[3]={0,2,3};for(int j=0;j<3;j++)for(int k=0;k<64;k++)bits[nr][j*64+k]='0'+((w[order[j]]>>(63-k))&1);
  int en=192;while(en && bits[nr][en-1]=='0')en--;end[nr]=en;nr++;}
 int best=0;
 for(int a=0;a<7;a++)for(int c=0;c<7;c++)for(int d=0;d<7;d++)for(int order=0;order<2;order++)for(int baseidx=0;baseidx<4;baseidx++)for(int pol=0;pol<2;pol++)for(int sign=0;sign<2;sign++)for(int kind=0;kind<2;kind++){
  int map[4]={a,c,d,0},bases[4]={0,8,10,12},base=bases[baseidx],exact=0,valid=0;
  for(unsigned r=0;r<nr;r++){int p=run(bits[r],hdr[r],map,order,base,pol,sign,kind);if(p>=0){valid++;if(p>=end[r] && p-end[r]<=8)exact++;}}
  if(exact>best){best=exact;printf("best %d/%u valid=%d map=%d,%d,%d,0 order=%d base=%d pol=%d sign=%d kind=%d\n",best,nr,valid,a,c,d,order,base,pol,sign,kind);fflush(stdout);}
 }
 return 0;
}