#include "nx300m_ycc420_multimodel_probe.h"
#include <math.h>
#include <string.h>
#include <limits.h>

/* Independent, small deterministic same-stage sampling. These four matrix /
 * range models are hypotheses, not observed Samsung ISP transfer functions. */
static uint8_t u8(double x){
 long n=lround(x);
 return (uint8_t)(n<0?0:n>255?255:n);
}
static unsigned delta(unsigned a,unsigned b){return a>b?a-b:b-a;}
static uint32_t mean1000(uint64_t sum,uint64_t count){
 return count?(uint32_t)((sum*1000u+count/2u)/count):UINT32_MAX;
}
static void convert(const uint8_t *rgb,unsigned model,uint8_t out[3]){
 const double kr=(model==NX_420_BT709_FULL||
                  model==NX_420_BT709_LIMITED)?0.2126:0.299;
 const double kb=(model==NX_420_BT709_FULL||
                  model==NX_420_BT709_LIMITED)?0.0722:0.114;
 const double g=1.0-kr-kb;
 double yy=kr*rgb[0]+g*rgb[1]+kb*rgb[2];
 double cb=128.0+(rgb[2]-yy)/(2.0*(1.0-kb));
 double cr=128.0+(rgb[0]-yy)/(2.0*(1.0-kr));
 if(model>=NX_420_BT601_LIMITED){
  yy=16.0+yy*219.0/255.0;
  cb=128.0+(cb-128.0)*224.0/255.0;
  cr=128.0+(cr-128.0)*224.0/255.0;
 }
 out[0]=u8(yy);out[1]=u8(cb);out[2]=u8(cr);
}
const char *nx_420_model_name(enum nx_420_model model){
 switch(model){
 case NX_420_BT601_FULL:return "BT601_FULL";
 case NX_420_BT709_FULL:return "BT709_FULL";
 case NX_420_BT601_LIMITED:return "BT601_LIMITED";
 case NX_420_BT709_LIMITED:return "BT709_LIMITED";
 default:return "UNKNOWN";
 }
}
enum nx_420_model_verdict nx_420_multimodel_probe(
 const uint8_t *y,size_t y_bytes,size_t y_stride,
 const uint8_t *c,size_t c_bytes,size_t c_stride,
 const uint8_t *rgb,size_t rgb_bytes,size_t rgb_stride,
 unsigned width,unsigned height,nx_420_model_report *out){
 if(out)memset(out,0,sizeof(*out));
 if(!out||!y||!c||!rgb||width<4||height<4||width>8192||
    height>8192||(width&1u)||(height&1u)||y_stride<width||
    c_stride<width||rgb_stride<(size_t)width*3u||
    y_stride>65536||c_stride>65536||rgb_stride>65536)return NX_420_MODEL_INVALID;
 const uint64_t need_y=(uint64_t)(height-1u)*y_stride+width;
 const uint64_t need_c=(uint64_t)(height/2u-1u)*c_stride+width;
 const uint64_t need_rgb=(uint64_t)(height-1u)*rgb_stride+
                           (uint64_t)width*3u;
 if(need_y>y_bytes||need_c>c_bytes||need_rgb>rgb_bytes)
  return NX_420_MODEL_INVALID;
 const unsigned half_w=width/2u,half_h=height/2u;
 const unsigned dx=(half_w+63u)/64u,dy=(half_h+63u)/64u;
 uint64_t yerror[NX_420_MODEL_COUNT]={0};
 uint64_t cerror[NX_420_MODEL_COUNT][2]={{0}};
 uint64_t informative[NX_420_MODEL_COUNT]={0};
 uint64_t sampled=0;
 for(unsigned yy=0;yy<half_h;yy+=dy){
  const uint8_t *y0=y+2u*(size_t)yy*y_stride;
  const uint8_t *y1=y0+y_stride;
  const uint8_t *ref0=rgb+2u*(size_t)yy*rgb_stride;
  const uint8_t *ref1=ref0+rgb_stride;
  const uint8_t *cc=c+(size_t)yy*c_stride;
  for(unsigned xx=0;xx<half_w;xx+=dx){
   const unsigned x=2u*xx;
   for(unsigned m=0;m<NX_420_MODEL_COUNT;m++){
    unsigned cb=0,cr=0;
    for(unsigned yy2=0;yy2<2;yy2++){
     const uint8_t *reference=yy2?ref1:ref0;
     const uint8_t *lum=yy2?y1:y0;
     for(unsigned x2=0;x2<2;x2++){
      uint8_t expect[3];
      convert(reference+(size_t)(x+x2)*3u,m,expect);
      yerror[m]+=delta(lum[x+x2],expect[0]);
      cb+=expect[1];cr+=expect[2];
     }
    }
    cb=(cb+2u)/4u;cr=(cr+2u)/4u;
    if(delta(cb,cr)>=18u)informative[m]++;
    cerror[m][0]+=delta(cc[x],cb)+delta(cc[x+1u],cr);
    cerror[m][1]+=delta(cc[x],cr)+delta(cc[x+1u],cb);
   }
   sampled++;
  }
 }
 out->sampled_pairs=sampled;
 uint32_t best=UINT32_MAX,second=UINT32_MAX;
 unsigned winner_model=0,winner_order=0;
 for(unsigned m=0;m<NX_420_MODEL_COUNT;m++){
  for(unsigned o=0;o<2;o++){
   nx_420_model_score *s=&out->candidates[m][o];
   s->y_mae_milli=mean1000(yerror[m],sampled*4u);
   s->chroma_mae_milli=mean1000(cerror[m][o],sampled*2u);
   s->combined_mae_milli=s->y_mae_milli+s->chroma_mae_milli;
   if(s->combined_mae_milli<best){
    second=best;best=s->combined_mae_milli;winner_model=m;winner_order=o;
   }else if(s->combined_mae_milli<second){
    second=s->combined_mae_milli;
   }
  }
 }
 out->best_model=(enum nx_420_model)winner_model;
 out->best_order=(enum nx_420_order)winner_order;
 out->informative_pairs=informative[winner_model];
 out->best_gap_milli=second-best;
 const nx_420_model_score *s=&out->candidates[winner_model][winner_order];
 if(sampled>=16u&&informative[winner_model]>=8u&&
    informative[winner_model]*10u>=sampled&&
    s->y_mae_milli<=8000u&&s->chroma_mae_milli<=6000u&&
    out->best_gap_milli>=2500u){
  out->verdict=NX_420_MODEL_DISTINCT;
 }else out->verdict=NX_420_MODEL_INCONCLUSIVE;
 return out->verdict;
}
