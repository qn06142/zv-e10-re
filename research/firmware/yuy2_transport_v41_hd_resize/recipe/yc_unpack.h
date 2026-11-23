#ifndef YC_UNPACK_H
#define YC_UNPACK_H
/* Candidate packing: U,Y0,V,Y1 -> Y0,U,Y1,V. Native source bytes must be
 * preserved for hardware verification; this permutation does not prove format. */
void yc_uyvy_to_yuy2(unsigned char *,const unsigned char *,unsigned);
#endif
