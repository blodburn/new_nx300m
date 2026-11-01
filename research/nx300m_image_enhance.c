#include "nx300m_image_enhance.h"
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
static int absi(int a){return a<0?-a:a;}
static int clip(int x,int lo,int hi){return x<lo?lo:x>hi?hi:x;}
static uint8_t u8(int x){return (uint8_t)clip(x,0,255);}
static int y709(const uint8_t *p){
    return (54*(int)p[0]+183*(int)p[1]+19*(int)p[2]+128)>>8;
}
int nx_image_enhance_rgb888(uint8_t *pixels,size_t stride,
                           unsigned width,unsigned height){
    if(!pixels||width==0||height==0||width>16384||height>16384||
       stride<(size_t)width*3u||
       (size_t)height>SIZE_MAX/stride||
       (size_t)height>SIZE_MAX/(size_t)width)return -1;
    const size_t bytes=(size_t)height*stride;
    const size_t n=(size_t)width*height;
    uint8_t *original=malloc(bytes),*luma=malloc(n);
    if(!original||!luma){free(original);free(luma);return -1;}
    memcpy(original,pixels,bytes);
    for(unsigned y=0;y<height;y++){
        const uint8_t *row=original+(size_t)y*stride;
        for(unsigned x=0;x<width;x++)
            luma[(size_t)y*width+x]=u8(y709(row+3u*x));
    }
    for(unsigned y=0;y<height;y++){
        const uint8_t *row=original+(size_t)y*stride;
        uint8_t *dst=pixels+(size_t)y*stride;
        for(unsigned x=0;x<width;x++){
            const uint8_t *p=row+3u*x;
            const int y0=luma[(size_t)y*width+x];
            const int r0=p[0]-y0,b0=p[2]-y0;
            int sr=4*r0,sb=4*b0,wt=4;
            const unsigned loY=y>0?y-1:y;
            const unsigned hiY=y+1<height?y+1:y;
            const unsigned loX=x>0?x-1:x;
            const unsigned hiX=x+1<width?x+1:x;
            int sumL=0,numL=0;
            for(unsigned ny=loY;ny<=hiY;ny++){
                const uint8_t *neigh=original+(size_t)ny*stride;
                for(unsigned nx=loX;nx<=hiX;nx++){
                    if(ny==y&&nx==x)continue;
                    const int yy=luma[(size_t)ny*width+nx];
                    const int dr=neigh[3u*nx]-yy,db=neigh[3u*nx+2]-yy;
                    const int dist=absi(yy-y0);
                    if(dist<=15&&absi(dr-r0)<=38&&absi(db-b0)<=38){
                        const int w=(ny==y||nx==x)?2:1;
                        sr+=w*dr;sb+=w*db;wt+=w;
                    }
                    if((ny==y||nx==x)&&dist<=8){sumL+=yy;numL++;}
                }
            }
            /* Reduce mainly SHADOW color noise. No cross-edge bleed. */
            const int mix=y0<72?224:(y0<144?160:64);
            const int dr=r0+((sr/wt-r0)*mix + ((sr/wt-r0)>=0?128:-128))/256;
            const int db=b0+((sb/wt-b0)*mix + ((sb/wt-b0)>=0?128:-128))/256;
            int yt=y0;
            if(y0<128&&numL>=3)
                yt=(3*y0+(sumL+numL/2)/numL+2)/4;
            /* Midtone-limited unsharp detail. Flat fields and hard edges stay
             * stable; shadows and blown highlights are not exaggerated. */
            if(x>0&&x+1<width&&y>0&&y+1<height&&y0>=32&&y0<=223){
                const int top=luma[(size_t)(y-1)*width+x];
                const int bottom=luma[(size_t)(y+1)*width+x];
                const int left=luma[(size_t)y*width+x-1];
                const int right=luma[(size_t)y*width+x+1];
                const int dmax=absi(y0-top)>absi(y0-bottom)?
                    absi(y0-top):absi(y0-bottom);
                const int maxdiff=dmax>absi(y0-left)?dmax:absi(y0-left);
                const int span=maxdiff>absi(y0-right)?maxdiff:absi(y0-right);
                if(span>=2&&span<=45){
                    const int highpass=y0-(top+bottom+left+right+2)/4;
                    const int gain=(y0<72)?3:6;
                    yt+=clip(highpass/2,-gain,gain);
                }
            }
            yt=clip(yt,0,255);
            const int rr=clip(yt+dr,0,255);
            const int bb=clip(yt+db,0,255);
            /* Recompute green from 709 luma to protect brightness, instead
             * of blurring all RGB channels or boosting noisy green. */
            const int gg=clip((256*yt-54*rr-19*bb+91)/183,0,255);
            dst[3u*x]=u8(rr);dst[3u*x+1]=u8(gg);dst[3u*x+2]=u8(bb);
        }
    }
    free(luma);free(original);
    return 0;
}
int nx_image_enhance_rgb888_row(const uint8_t *prev,
                               const uint8_t *cur,
                               const uint8_t *next,
                               uint8_t *out,unsigned width,
                               unsigned y,unsigned height){
    if(!cur||!out||!width||width>16384||!height||height>16384||
       y>=height||(y>0&&!prev)||(y+1<height&&!next))return -1;
    if(!prev)prev=cur;
    if(!next)next=cur;
    for(unsigned x=0;x<width;x++){
        const uint8_t *p=cur+3u*x;
        const int y0=y709(p);
        const int r0=p[0]-y0,b0=p[2]-y0;
        int sr=4*r0,sb=4*b0,wt=4,sumL=0,numL=0;
        for(int dy=-1;dy<=1;dy++){
            if((dy==-1&&y==0)||(dy==1&&y+1==height))continue;
            const uint8_t *src=dy<0?prev:dy>0?next:cur;
            const unsigned loX=x>0?x-1:x;
            const unsigned hiX=x+1<width?x+1:x;
            for(unsigned nx=loX;nx<=hiX;nx++){
                if(dy==0&&nx==x)continue;
                const uint8_t *q=src+3u*nx;
                const int yy=y709(q);
                const int dr=q[0]-yy,db=q[2]-yy;
                const int dist=absi(yy-y0);
                if(dist<=15&&absi(dr-r0)<=38&&absi(db-b0)<=38){
                    const int w=(dy==0||nx==x)?2:1;
                    sr+=w*dr;sb+=w*db;wt+=w;
                }
                if((dy==0||nx==x)&&dist<=8){sumL+=yy;numL++;}
            }
        }
        const int mix=y0<72?224:(y0<144?160:64);
        const int dr0=sr/wt-r0,db0=sb/wt-b0;
        const int dr=r0+(dr0*mix+(dr0>=0?128:-128))/256;
        const int db=b0+(db0*mix+(db0>=0?128:-128))/256;
        int yt=y0;
        if(y0<128&&numL>=3)yt=(3*y0+(sumL+numL/2)/numL+2)/4;
        if(x>0&&x+1<width&&y>0&&y+1<height&&y0>=32&&y0<=223){
            const int top=y709(prev+3u*x);
            const int bottom=y709(next+3u*x);
            const int left=y709(cur+3u*(x-1));
            const int right=y709(cur+3u*(x+1));
            const int m=absi(y0-top)>absi(y0-bottom)?absi(y0-top):absi(y0-bottom);
            const int m2=m>absi(y0-left)?m:absi(y0-left);
            const int span=m2>absi(y0-right)?m2:absi(y0-right);
            if(span>=2&&span<=45){
                const int highpass=y0-(top+bottom+left+right+2)/4;
                yt+=clip(highpass/2,-(y0<72?3:6),y0<72?3:6);
            }
        }
        yt=clip(yt,0,255);
        const int rr=clip(yt+dr,0,255),bb=clip(yt+db,0,255);
        const int gg=clip((256*yt-54*rr-19*bb+91)/183,0,255);
        out[3u*x]=u8(rr);out[3u*x+1]=u8(gg);out[3u*x+2]=u8(bb);
    }
    return 0;
}
