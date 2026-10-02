"""Original, deterministic ink-marbling and pigment-particle GPU module.

No reference media is embedded. This is an artistic flow-field renderer, not a
Navier-Stokes simulation. Its bounded shader has no feedback history, so cue
seeking and manual time are reproducible without a warm-up or reset.
"""


def _control(name, label, page, default, minimum=0.0, maximum=1.0, **extra):
    return dict(name=name, label=label, page=page, default=default,
                type="float", min=minimum, max=maximum, **extra)


PARAMETERS = (
    dict(name="Enabled", label="Module Enabled", page="Ink Dream Flow", type="toggle", default=True),
    _control("Mix", "Effect Mix", "Ink Dream Flow", 1.0, uniform="uMix"),
    dict(name="Background", label="Background", page="Ink Dream Flow", type="menu", default="paper",
         menu_names=["paper", "source", "transparent"], menu_labels=["Procedural Xuan Paper", "Input Image / Paper", "Transparent Ink"], uniform="uBackground"),
    dict(name="Autotime", label="Auto Time", page="Timing", type="toggle", default=True),
    _control("Timescale", "Time Scale (0 = Freeze)", "Timing", 1.0, -5.0, 5.0),
    _control("Manualtime", "Manual Time", "Timing", 0.0, -100000.0, 100000.0, norm_min=0.0, norm_max=60.0),
    _control("Time", "Effective Time", "Timing", 0.0, -500000.0, 500000.0, uniform="uTime", read_only=True, animatable=False),
    dict(name="Seed", label="Random Seed", page="Timing", type="int", default=27, min=0, max=100000, uniform="uSeed"),
    dict(name="Center", label="Composition Center", page="Composition", type="xy", default=[0.0, 0.0], min=-1.0, max=1.0, uniform="uCenter"),
    _control("Scale", "Pattern Scale", "Composition", 1.25, 0.2, 6.0, uniform="uScale"),
    _control("Rotation", "Pattern Rotation", "Composition", -18.0, -180.0, 180.0, uniform="uRotation"),
    _control("Coverage", "Ink Coverage", "Composition", 0.48, 0.0, 1.0, uniform="uCoverage"),
    _control("Spread", "Composition Spread", "Composition", 0.78, 0.1, 2.0, uniform="uSpread"),
    _control("Stretch", "Ribbon Stretch", "Composition", 1.8, 0.25, 5.0, uniform="uStretch"),
    dict(name="Liquidenabled", label="Liquid Ink Enabled", page="Liquid Flow", type="toggle", default=True, uniform="uLiquidEnabled"),
    _control("Flowamount", "Flow Deformation", "Liquid Flow", 0.85, 0.0, 2.0, uniform="uFlowAmount"),
    _control("Flowspeed", "Liquid Speed / Reverse", "Liquid Flow", 0.28, -3.0, 3.0, uniform="uFlowSpeed"),
    _control("Direction", "Drift Direction", "Liquid Flow", 25.0, -180.0, 180.0, uniform="uDirection"),
    _control("Drift", "Directional Drift", "Liquid Flow", 0.12, 0.0, 1.0, uniform="uDrift"),
    _control("Swirl", "Vortex Curl", "Liquid Flow", 1.35, 0.0, 4.0, uniform="uSwirl"),
    _control("Turbulence", "Small Flow Turbulence", "Liquid Flow", 0.38, 0.0, 1.5, uniform="uTurbulence"),
    _control("Wander", "Dream Wandering", "Liquid Flow", 0.38, 0.0, 1.0, uniform="uWander"),
    _control("Marbling", "Marbled Filaments", "Ink Surface", 0.68, 0.0, 1.0, uniform="uMarbling"),
    _control("Filaments", "Filament Frequency", "Ink Surface", 18.0, 2.0, 60.0, uniform="uFilaments"),
    _control("Inkamount", "Deep Ink Strength", "Ink Surface", 0.82, 0.0, 1.0, uniform="uInkAmount"),
    _control("Washamount", "Diluted Wash Strength", "Ink Surface", 0.62, 0.0, 1.0, uniform="uWashAmount"),
    _control("Bleed", "Wet Edge Bleed", "Ink Surface", 0.38, 0.0, 1.0, uniform="uBleed"),
    _control("Edge", "Pigment Edge Pooling", "Ink Surface", 0.32, 0.0, 1.0, uniform="uEdge"),
    _control("Granulation", "Pigment Granulation", "Ink Surface", 0.32, 0.0, 1.0, uniform="uGranulation"),
    _control("Drybrush", "Dry Brush Fibers", "Ink Surface", 0.18, 0.0, 1.0, uniform="uDryBrush"),
    dict(name="Particlesenabled", label="Pigment Particles Enabled", page="Particles", type="toggle", default=True, uniform="uParticlesEnabled"),
    _control("Particleamount", "Particle Opacity", "Particles", 0.62, 0.0, 1.0, uniform="uParticleAmount"),
    _control("Particledensity", "Particle Density", "Particles", 0.56, 0.0, 1.0, uniform="uParticleDensity"),
    _control("Particlesize", "Particle Size", "Particles", 1.4, 0.3, 8.0, uniform="uParticleSize"),
    _control("Particlesoftness", "Particle Softness", "Particles", 0.3, 0.0, 1.0, uniform="uParticleSoftness"),
    _control("Particlespeed", "Particle Speed / Reverse", "Particles", 0.35, -3.0, 3.0, uniform="uParticleSpeed"),
    _control("Particlejitter", "Random Particle Wandering", "Particles", 0.48, 0.0, 1.0, uniform="uParticleJitter"),
    _control("Particleflow", "Particle Flow Distortion", "Particles", 0.65, 0.0, 1.0, uniform="uParticleFlow"),
    _control("Particlespread", "Particles Outside Liquid", "Particles", 0.28, 0.0, 1.0, uniform="uParticleSpread"),
    _control("Particletrail", "Particle Streak Length", "Particles", 0.2, 0.0, 1.0, uniform="uParticleTrail"),
    dict(name="Glitterenabled", label="Glitter Enabled", page="Glitter", type="toggle", default=False, uniform="uGlitterEnabled"),
    _control("Glitteramount", "Glitter Amount (0 = Off)", "Glitter", 0.7, 0.0, 2.0, uniform="uGlitterAmount"),
    _control("Glitterdensity", "Glitter Density", "Glitter", 0.45, uniform="uGlitterDensity"),
    _control("Glittersize", "Glitter Grain Size (Pixels)", "Glitter", 2.2, 0.3, 6.0, uniform="uGlitterSize"),
    _control("Glittersoftness", "Glitter Grain Softness", "Glitter", 0.2, uniform="uGlitterSoftness"),
    _control("Glitterbrightness", "Glitter Brightness (0 = Off)", "Glitter", 1.4, 0.0, 8.0, uniform="uGlitterBrightness"),
    dict(name="Glittercolor", label="Glitter Color / Opacity", page="Glitter", type="rgba", default=[0.76, 0.9, 1.0, 1.0], uniform="uGlitterColor"),
    dict(name="Glittersurface", label="Glitter Surface", page="Glitter", type="menu", default="combined",
         menu_names=["ink", "wash", "particles", "combined"], menu_labels=["Deep Ink", "Diluted Wash", "Pigment Particles", "Ink + Wash + Particles"], uniform="uGlitterSurface"),
    _control("Glitterthreshold", "Surface Threshold", "Glitter", 0.12, uniform="uGlitterThreshold"),
    _control("Glitteredge", "Surface Edge Softness", "Glitter", 0.08, 0.001, 0.5, uniform="uGlitterEdge"),
    _control("Glitterspread", "Glitter Outside Ink", "Glitter", 0.0, uniform="uGlitterSpread"),
    _control("Glitterspeed", "Glitter Drift Speed / Reverse", "Glitter Motion", 0.25, -4.0, 4.0, uniform="uGlitterSpeed"),
    _control("Glitterdirection", "Glitter Drift Direction", "Glitter Motion", 25.0, -180.0, 180.0, uniform="uGlitterDirection"),
    _control("Glitterflow", "Glitter Flow Distortion", "Glitter Motion", 0.35, uniform="uGlitterFlow"),
    _control("Glitterjitter", "Glitter Random Wandering", "Glitter Motion", 0.35, uniform="uGlitterJitter"),
    dict(name="Glitterseed", label="Glitter Random Seed", page="Glitter Motion", type="int", default=71, min=0, max=100000, uniform="uGlitterSeed"),
    _control("Glittershimmer", "Glitter Shimmer Amount", "Glitter Motion", 0.75, uniform="uGlitterShimmer"),
    _control("Glittertwinklespeed", "Shimmer Speed (0 = Freeze)", "Glitter Motion", 1.1, 0.0, 8.0, uniform="uGlitterTwinkleSpeed"),
    _control("Glitterstars", "Star Highlight Amount", "Glitter Highlights", 0.2, uniform="uGlitterStars"),
    _control("Glitterstarlength", "Star Highlight Length", "Glitter Highlights", 1.8, 1.0, 3.0, uniform="uGlitterStarLength"),
    _control("Glitterstarrotation", "Star Highlight Rotation", "Glitter Highlights", 0.0, -180.0, 180.0, uniform="uGlitterStarRotation"),
    _control("Glitterglow", "Glitter Glow Amount", "Glitter Highlights", 0.2, 0.0, 2.0, uniform="uGlitterGlow"),
    _control("Glitterglowradius", "Glitter Glow Radius", "Glitter Highlights", 1.4, 0.5, 2.0, uniform="uGlitterGlowRadius"),
    dict(name="Staticglitterenabled", label="Static Glitter Enabled", page="Static Glitter", type="toggle", default=False, uniform="uStaticEnabled"),
    _control("Staticglitteramount", "Static Glitter Amount (0 = Off)", "Static Glitter", 0.6, 0.0, 2.0, uniform="uStaticAmount"),
    _control("Staticglitterdensity", "Static Glitter Density", "Static Glitter", 0.6, uniform="uStaticDensity"),
    _control("Staticglittersize", "Static Grain Radius (Pixels)", "Static Glitter", 1.0, 0.1, 2.0, uniform="uStaticSize"),
    _control("Staticglittersoftness", "Static Grain Softness", "Static Glitter", 0.15, uniform="uStaticSoftness"),
    _control("Staticglitterbrightness", "Static Glitter Brightness", "Static Glitter", 1.35, 0.0, 8.0, uniform="uStaticBrightness"),
    dict(name="Staticglittercolor", label="Static Glitter Color / Opacity", page="Static Glitter", type="rgba", default=[0.8, 0.87, 1.0, 1.0], uniform="uStaticColor"),
    dict(name="Staticglittersurface", label="Static Glitter Surface", page="Static Glitter", type="menu", default="combined",
         menu_names=["ink", "wash", "particles", "combined"], menu_labels=["Deep Ink", "Diluted Wash", "Pigment Particles", "Ink + Wash + Particles"], uniform="uStaticSurface"),
    _control("Staticglitterthreshold", "Static Surface Threshold", "Static Glitter", 0.08, uniform="uStaticThreshold"),
    _control("Staticglitteredge", "Static Surface Edge Softness", "Static Glitter", 0.05, 0.001, 0.5, uniform="uStaticEdge"),
    _control("Staticglitterspread", "Static Glitter Outside Ink", "Static Glitter", 0.0, uniform="uStaticSpread"),
    dict(name="Staticglitterseed", label="Static Glitter Seed", page="Static Glitter", type="int", default=137, min=0, max=100000, uniform="uStaticSeed"),
    _control("Staticglitterstars", "Static Star Amount", "Static Highlights", 0.08, uniform="uStaticStars"),
    _control("Staticglitterstarlength", "Static Star Length", "Static Highlights", 1.8, 1.0, 3.0, uniform="uStaticStarLength"),
    _control("Staticglitterstarrotation", "Static Star Rotation", "Static Highlights", 0.0, -180.0, 180.0, uniform="uStaticStarRotation"),
    _control("Staticglitterglow", "Static Glow Amount", "Static Highlights", 0.1, 0.0, 2.0, uniform="uStaticGlow"),
    _control("Staticglitterglowradius", "Static Glow Radius", "Static Highlights", 1.4, 0.5, 2.0, uniform="uStaticGlowRadius"),
    _control("Staticglittershimmer", "Static Shimmer Amount (0 = Still)", "Static Shimmer", 0.0, uniform="uStaticShimmer"),
    _control("Staticglittertwinklespeed", "Static Shimmer Speed / Reverse", "Static Shimmer", 1.15, -8.0, 8.0, uniform="uStaticTwinkleSpeed"),
    _control("Staticglittershimmercontrast", "Static Shimmer Sharpness", "Static Shimmer", 3.0, 0.25, 8.0, uniform="uStaticShimmerContrast"),
    _control("Staticglittershimmerfloor", "Static Shimmer Minimum Brightness", "Static Shimmer", 0.22, uniform="uStaticShimmerFloor"),
    _control("Staticglittershimmerrandom", "Static Shimmer Phase Variation", "Static Shimmer", 1.0, uniform="uStaticShimmerRandom"),
    _control("Papertexture", "Paper Fiber Strength", "Paper", 0.28, 0.0, 1.0, uniform="uPaperTexture"),
    _control("Papergrain", "Paper Grain Scale", "Paper", 1.0, 0.25, 4.0, uniform="uPaperGrain"),
    _control("Vignette", "Paper Edge Aging", "Paper", 0.18, 0.0, 1.0, uniform="uVignette"),
    dict(name="Inkcolor", label="Deep Ink Color", page="Palette", type="rgba", default=[0.025, 0.035, 0.105, 1.0], uniform="uInkColor"),
    dict(name="Washcolor", label="Diluted Wash Color", page="Palette", type="rgba", default=[0.27, 0.32, 0.43, 1.0], uniform="uWashColor"),
    dict(name="Particlecolor", label="Pigment Particle Color", page="Palette", type="rgba", default=[0.07, 0.09, 0.19, 1.0], uniform="uParticleColor"),
    dict(name="Papercolor", label="Paper Color", page="Palette", type="rgba", default=[0.94, 0.85, 0.67, 1.0], uniform="uPaperColor"),
)


SHADER = r"""
layout(location = 0) out vec4 fragColor;
uniform float uMix, uBackground, uTime, uSeed;
uniform vec2 uCenter;
uniform float uScale, uRotation, uCoverage, uSpread, uStretch;
uniform float uLiquidEnabled, uFlowAmount, uFlowSpeed, uDirection, uDrift;
uniform float uSwirl, uTurbulence, uWander, uMarbling, uFilaments;
uniform float uInkAmount, uWashAmount, uBleed, uEdge, uGranulation, uDryBrush;
uniform float uParticlesEnabled, uParticleAmount, uParticleDensity, uParticleSize;
uniform float uParticleSoftness, uParticleSpeed, uParticleJitter, uParticleFlow;
uniform float uParticleSpread, uParticleTrail, uPaperTexture, uPaperGrain, uVignette;
uniform vec4 uInkColor, uWashColor, uParticleColor, uPaperColor;
uniform float uGlitterEnabled, uGlitterAmount, uGlitterDensity, uGlitterSize;
uniform float uGlitterSoftness, uGlitterBrightness, uGlitterSurface, uGlitterThreshold;
uniform float uGlitterEdge, uGlitterSpread, uGlitterSpeed, uGlitterDirection;
uniform float uGlitterFlow, uGlitterJitter, uGlitterSeed, uGlitterShimmer;
uniform float uGlitterTwinkleSpeed, uGlitterStars, uGlitterStarLength, uGlitterStarRotation;
uniform float uGlitterGlow, uGlitterGlowRadius;
uniform vec4 uGlitterColor;
uniform float uStaticEnabled, uStaticAmount, uStaticDensity, uStaticSize;
uniform float uStaticSoftness, uStaticBrightness, uStaticSurface, uStaticThreshold;
uniform float uStaticEdge, uStaticSpread, uStaticSeed, uStaticStars;
uniform float uStaticStarLength, uStaticStarRotation, uStaticGlow, uStaticGlowRadius;
uniform float uStaticShimmer, uStaticTwinkleSpeed, uStaticShimmerContrast;
uniform float uStaticShimmerFloor, uStaticShimmerRandom;
uniform vec4 uStaticColor;

float hash21(vec2 p) {
    vec3 q = fract(vec3(p.xyx) * .1031);
    q += dot(q, q.yzx + 33.33);
    return fract((q.x + q.y) * q.z);
}
float noise2(vec2 p) {
    vec2 i=floor(p), f=fract(p); f=f*f*(3.-2.*f);
    return mix(mix(hash21(i),hash21(i+vec2(1,0)),f.x),
               mix(hash21(i+vec2(0,1)),hash21(i+vec2(1,1)),f.x),f.y);
}
mat2 rot(float a) { float c=cos(a), s=sin(a); return mat2(c,-s,s,c); }
float fbm(vec2 p) {
    float v=0., a=.53;
    for(int i=0;i<4;i++) { v+=a*noise2(p); p=rot(.53)*p*2.07+17.1; a*=.47; }
    return v;
}
vec2 flow(vec2 p, float t, float seed) {
    vec2 q=p;
    // Smoothly wandering vortex centers: a bounded inverse coordinate map.
    // No per-frame random reseeding, no feedback accumulation, no singularities.
    for(int i=0;i<3;i++) {
        float k=float(i), phase=seed*.13+k*2.094;
        vec2 c=.72*vec2(cos(phase+t*.31),sin(phase*1.7+t*.27));
        c+=uWander*.34*vec2(sin(t*.49+k),cos(t*.37-k));
        vec2 d=q-c;
        float turn=uSwirl*uFlowAmount*(i==1 ? -1. : 1.)*2.1*exp(-dot(d,d)*1.2);
        q=c+rot(turn)*d;
    }
    vec2 n=vec2(fbm(q*2.3+seed+t*.11),fbm(q*2.3-seed-t*.09+31.7))-.5;
    q+=n*uTurbulence*uFlowAmount;
    return q;
}
// Straight-color over, stored internally as premultiplied RGBA.
vec4 overInk(vec4 base, vec4 ink, float amount) {
    float a=clamp(ink.a*amount,0.,1.);
    return vec4(ink.rgb*a + base.rgb*(1.-a), a+base.a*(1.-a));
}
float grains(vec2 p, float t, float seed) {
    // Fixed grid spacing makes radius and density independent controls.
    vec2 g=p*135.0 + t*vec2(2.2,-1.3);
    vec2 cell=floor(g), f=fract(g);
    float dots=0.;
    if(uParticleDensity<=0.) return 0.;
    float radius=uParticleSize/16.0;
    for(int y=-1;y<=1;y++) for(int x=-1;x<=1;x++) {
        vec2 offset=vec2(x,y), id=cell+offset;
        float h=hash21(id+seed), h2=hash21(id+seed+37.2);
        vec2 center=.5+.32*vec2(sin(h*6.283+t),cos(h2*6.283+t*.73))*uParticleJitter;
        vec2 d=rot(.7)*(f-offset-center);
        d.x/=1.+uParticleTrail;
        float r=radius*mix(.35,1.,h2);
        float aa=max(fwidth(length(d)),.008);
        float dotMask=1.-smoothstep(max(0.,r*(1.-uParticleSoftness)-aa),r+aa,length(d));
        dots=max(dots,dotMask*step(h,clamp(uParticleDensity,0.,1.)));
    }
    return dots;
}
vec3 glitterGrains(vec2 screen, float height, float seed) {
    // Fixed 16-pixel cells keep grain radius independent of density. Nine
    // neighbors support soft grains, star arms and halos across cell borders.
    float gt=uTime*uGlitterSpeed;
    float gs=seed+uGlitterSeed*.719+13.1;
    vec2 direction=vec2(cos(radians(uGlitterDirection)),sin(radians(uGlitterDirection)));
    vec2 coord=mix(screen,flow(screen,gt,gs),uGlitterFlow);
    vec2 g=(coord*height+direction*gt*8.)/16.;
    vec2 cell=floor(g), f=fract(g);
    float aa=max(length(fwidth(g))*.55,.008);
    vec3 lights=vec3(0.);
    if(uGlitterDensity<=0.) return lights;
    for(int y=-1;y<=1;y++) for(int x=-1;x<=1;x++) {
        vec2 id=cell+vec2(x,y);
        float h=hash21(id+gs), h2=hash21(id+gs+37.2);
        float alive=step(h,clamp(uGlitterDensity,0.,1.));
        vec2 center=.5+.32*vec2(sin(h*6.283+gt),cos(h2*6.283+gt*.73))*uGlitterJitter;
        vec2 d=f-vec2(x,y)-center;
        float distance=length(d), radius=uGlitterSize/16.*mix(.45,1.,h2);
        float grain=1.-smoothstep(max(0.,radius*(1.-uGlitterSoftness)-aa),radius+aa,distance);
        float pulse=.5+.5*sin(uTime*uGlitterTwinkleSpeed*6.2831853+h2*31.4159265);
        float shimmer=mix(1.,.12+.88*pow(pulse,4.),uGlitterShimmer);
        vec2 starCoord=rot(radians(uGlitterStarRotation))*d;
        float arm=min(radius*uGlitterStarLength,.7);
        float thickness=max(radius*.16,aa);
        float star=(1.-smoothstep(thickness,thickness+aa,abs(starCoord.x)))
                   *(1.-smoothstep(arm*.2,arm+aa,abs(starCoord.y)));
        star+=(1.-smoothstep(thickness,thickness+aa,abs(starCoord.y)))
              *(1.-smoothstep(arm*.2,arm+aa,abs(starCoord.x)));
        star*=uGlitterStars*step(hash21(id+gs+83.4),.18);
        float haloRadius=max(radius*uGlitterGlowRadius,.008);
        float halo=exp(-dot(d,d)/(haloRadius*haloRadius))
                   *(1.-smoothstep(.65,.9,distance))*uGlitterGlow;
        lights=max(lights,vec3(grain,star,halo)*alive*shimmer);
    }
    return lights;
}
// Paper-aligned fine mineral grains, inspired by the Calligraphic Shadow
// texture. Centers never move. Optional Calligraphic-style shimmer changes
// brightness only; the ink mask can move independently beneath the grains.
vec3 staticGlitterGrains(vec2 screen, float height, float seed) {
    vec2 g=screen*height/6.;
    vec2 cell=floor(g), f=fract(g);
    float gs=seed+uStaticSeed*.719+91.3;
    float aa=max(length(fwidth(g))*.55,.008);
    vec3 lights=vec3(0.);
    if(uStaticDensity<=0.) return lights;
    for(int y=-1;y<=1;y++) for(int x=-1;x<=1;x++) {
        vec2 id=cell+vec2(x,y);
        float h=hash21(id+gs), h2=hash21(id+gs+37.2);
        vec2 center=.18+.64*vec2(hash21(id+gs+11.),hash21(id+gs+23.));
        vec2 d=f-vec2(x,y)-center;
        float radius=uStaticSize/6.*mix(.4,1.,h2), distance=length(d);
        float grain=1.-smoothstep(max(0.,radius*(1.-uStaticSoftness)-aa),radius+aa,distance);
        vec2 starCoord=rot(radians(uStaticStarRotation))*d;
        float arm=min(radius*uStaticStarLength,.8), thickness=max(radius*.16,aa);
        float star=(1.-smoothstep(thickness,thickness+aa,abs(starCoord.x)))
                   *(1.-smoothstep(arm*.2,arm+aa,abs(starCoord.y)));
        star+=(1.-smoothstep(thickness,thickness+aa,abs(starCoord.y)))
              *(1.-smoothstep(arm*.2,arm+aa,abs(starCoord.x)));
        star*=uStaticStars*step(hash21(id+gs+83.4),.12);
        float haloRadius=max(radius*uStaticGlowRadius,.008);
        float halo=exp(-dot(d,d)/(haloRadius*haloRadius))
                   *(1.-smoothstep(.65,.9,distance))*uStaticGlow;
        float pulse=.5+.5*sin(uTime*uStaticTwinkleSpeed*6.2831853
                              +h2*31.4159265*uStaticShimmerRandom);
        float twinkle=uStaticShimmerFloor+(1.6-uStaticShimmerFloor)
                      *pow(pulse,uStaticShimmerContrast);
        float shimmer=mix(1.,twinkle,uStaticShimmer);
        lights=max(lights,vec3(grain,star,halo)*step(h,clamp(uStaticDensity,0.,1.))*shimmer);
    }
    return lights;
}
void main() {
    vec2 uv=vUV.st;
    vec4 source=texture(sTD2DInputs[0],uv);
    if(uMix<=0.) { fragColor=TDOutputSwizzle(source); return; }
    float aspect=uTD2DInfos[0].res.z/max(uTD2DInfos[0].res.w,1.);
    vec2 screen=(uv-.5)*vec2(aspect,1.);
    vec2 p=rot(radians(uRotation))*(screen-uCenter)*uScale*2.;
    p.x/=max(uStretch,.25);
    float seed=uSeed*.719+7.31;
    float t=uTime*uFlowSpeed;
    vec2 direction=vec2(cos(radians(uDirection)),sin(radians(uDirection)));
    vec2 moving=p-direction*t*uDrift*.15;
    moving+=uWander*.18*vec2(sin(t*.53+seed),cos(t*.39+seed));
    vec2 q=flow(moving,t,seed);
    float n=fbm(q*2.15+seed);
    float fine=fbm(q*11.3+seed);
    float bands=.5+.5*sin((q.x*.74+q.y*.56+n*2.6)*uFilaments);
    float signal=mix(n,.48*n+.52*bands,uMarbling);
    // A soft envelope preserves the breathing room of the ink-wash series.
    float envelope=exp(-dot(p*vec2(.72,1.),p*vec2(.72,1.))/(uSpread*uSpread*3.));
    float threshold=mix(.88,.08,uCoverage);
    float edgeNoise=(fine-.5)*(.05+.14*uBleed);
    float width=.018+.18*uBleed;
    float field=signal*envelope+edgeNoise;
    float wet=smoothstep(threshold-width,threshold+width,field)*step(.0001,uCoverage);
    float wash=smoothstep(threshold-width*2.5-.09,threshold+.1,field)*step(.0001,uCoverage);
    float pool=exp(-abs(field-threshold)/(width*.28+.006))*wash;
    vec2 pixel=uv*uTD2DInfos[0].res.zw;
    float speck=hash21(floor(pixel)+seed);
    float fibers=noise2(q*vec2(480.,36.)+seed);
    float broken=mix(1.,smoothstep(.23,.8,fibers),uDryBrush);
    float granule=mix(1.,.4+.6*speck,uGranulation);
    float ink=clamp(wet*(.6+.4*signal)+pool*uEdge*.65,0.,1.)*broken*granule;
    float paperNoise=fbm(screen*40.*uPaperGrain+19.7);
    float paperFiber=noise2(screen*vec2(700.,180.)*uPaperGrain);
    float paperTone=1.+uPaperTexture*((paperNoise-.5)*.16+(paperFiber-.5)*.12);
    float rim=smoothstep(.2,.72,length((uv-.5)*vec2(1.,1.2)));
    vec3 paper=clamp(uPaperColor.rgb*paperTone*(1.-uVignette*rim*.3),0.,1.);
    vec4 result=vec4(paper*uPaperColor.a,uPaperColor.a);
    if(uBackground>.5 && uBackground<1.5) result=vec4(source.rgb*source.a,source.a);
    if(uBackground>1.5) result=vec4(0.);
    if(uLiquidEnabled>.5) {
        result=overInk(result,uWashColor,wash*uWashAmount*.64);
        result=overInk(result,uInkColor,ink*uInkAmount);
    }
    float particleSurface=0.;
    if(uParticlesEnabled>.5 && uParticleAmount>0.) {
        // Particle clock is independent; zero freezes grains even while ink moves.
        float pt=uTime*uParticleSpeed;
        vec2 pq=mix(p,flow(p,pt,seed),uParticleFlow);
        float particleMask=mix(wash,envelope,uParticleSpread);
        float dots=grains(pq,pt,seed);
        particleSurface=dots*particleMask*uParticleAmount*uParticleColor.a;
        result=overInk(result,uParticleColor,dots*particleMask*uParticleAmount);
    }
    if(uGlitterEnabled>.5 && uGlitterAmount>0. && uGlitterBrightness>0.) {
        float inkSurface=uLiquidEnabled>.5 ? ink*uInkAmount*uInkColor.a : 0.;
        float washSurface=uLiquidEnabled>.5 ? wash*uWashAmount*uWashColor.a*.64 : 0.;
        float carrier=max(max(inkSurface,washSurface),particleSurface);
        if(uGlitterSurface<.5) carrier=inkSurface;
        else if(uGlitterSurface<1.5) carrier=washSurface;
        else if(uGlitterSurface<2.5) carrier=particleSurface;
        carrier=mix(carrier,envelope,uGlitterSpread);
        float surface=smoothstep(uGlitterThreshold-uGlitterEdge,
                                 uGlitterThreshold+uGlitterEdge,carrier)*step(.00001,carrier);
        vec3 lights=glitterGrains(screen,uTD2DInfos[0].res.w,seed);
        float strength=surface*(lights.x+lights.y*.6+lights.z*.2)*uGlitterAmount;
        vec4 highlight=vec4(uGlitterColor.rgb*uGlitterBrightness,uGlitterColor.a);
        result=overInk(result,highlight,strength);
    }
    if(uStaticEnabled>.5 && uStaticAmount>0. && uStaticBrightness>0.) {
        float inkSurface=uLiquidEnabled>.5 ? ink*uInkAmount*uInkColor.a : 0.;
        float washSurface=uLiquidEnabled>.5 ? wash*uWashAmount*uWashColor.a*.64 : 0.;
        float carrier=max(max(inkSurface,washSurface),particleSurface);
        if(uStaticSurface<.5) carrier=inkSurface;
        else if(uStaticSurface<1.5) carrier=washSurface;
        else if(uStaticSurface<2.5) carrier=particleSurface;
        carrier=mix(carrier,envelope,uStaticSpread);
        float surface=smoothstep(uStaticThreshold-uStaticEdge,
                                 uStaticThreshold+uStaticEdge,carrier)*step(.00001,carrier);
        vec3 lights=staticGlitterGrains(screen,uTD2DInfos[0].res.w,seed);
        result=overInk(result,vec4(uStaticColor.rgb*uStaticBrightness,uStaticColor.a),
                       surface*(lights.x+lights.y*.6+lights.z*.2)*uStaticAmount);
    }
    // Public TOP contract uses straight alpha; transparent background is usable
    // with an Over TOP and never carries hidden paper RGB at alpha zero.
    result.rgb=result.a>1e-6 ? result.rgb/result.a : vec3(0.);
    fragColor=TDOutputSwizzle(mix(source,result,clamp(uMix,0.,1.)));
}
"""


def brush_variant():
    """Reference-first soft particle currents, retaining the stable module ID.

    Smooth noise contours supply broad luminous sheets around dark cavities.
    A bounded line-integral convolution follows their curl field, producing
    wispy particle streaks instead of hard cellular seams or dry ink hatching.
    All clocks are seekable; no tutorial code/media or feedback history is used.
    """
    import copy
    parameters = list(copy.deepcopy(PARAMETERS))
    defaults = dict(Coverage=.57, Spread=1.7, Marbling=.25, Filaments=28.,
                    Drybrush=0., Granulation=0., Bleed=.65, Edge=.2,
                    Particledensity=.72, Particlesize=.9, Particlesoftness=.65,
                    Particleamount=.65, Particletrail=.75, Particleflow=1.,
                    Particlespeed=.28, Particlejitter=.25, Particlespread=0., Inkamount=.4,
                    Washamount=.45, Swirl=.65, Stretch=1., Scale=.85,
                    Rotation=0., Flowamount=.65, Papertexture=.12, Vignette=.12,
                    Inkcolor=[.62,.73,1.,1.], Washcolor=[.10,.15,.25,1.],
                    Particlecolor=[.76,.85,1.,1.], Papercolor=[.012,.02,.045,1.])
    for definition in parameters:
        if definition["page"] == "Ink Dream Flow":
            definition["page"] = "Ink Brush Flow"
        if definition["name"] in defaults:
            definition["default"] = defaults[definition["name"]]
    parameters.extend((
        dict(name="Brushenabled", label="Particle Currents Enabled", page="Brush Currents", type="toggle", default=True, uniform="uBrushEnabled"),
        _control("Brushweb", "Soft Current Amount", "Brush Currents", 1., uniform="uBrushWeb"),
        _control("Brushscale", "Current / Cavity Scale", "Brush Currents", 3.2, 1., 12., uniform="uBrushScale"),
        _control("Brushwidth", "Soft Current Width", "Brush Currents", .09, .015, .35, uniform="uBrushWidth"),
        _control("Brushlength", "Wispy Streak Length", "Brush Currents", .72, uniform="uBrushLength"),
        _control("Brushfibers", "Fine Particle Wisps", "Brush Currents", 1., uniform="uBrushFibers"),
        _control("Brushcurl", "Current Curl", "Brush Currents", .75, 0., 2., uniform="uBrushCurl"),
        _control("Brushcontrast", "Current Contrast", "Brush Currents", 1.0, .3, 4., uniform="uBrushContrast"),
        _control("Brushglow", "Current Core Glow", "Brush Currents", 1.5, 0., 3., uniform="uBrushGlow"),
        _control("Brushhaze", "Soft Current Haze", "Brush Currents", .5, uniform="uBrushHaze"),
    ))
    shader = SHADER.replace("float hash21(vec2 p)",
        "uniform float uBrushEnabled, uBrushWeb, uBrushScale, uBrushWidth;\n"
        "uniform float uBrushLength, uBrushFibers, uBrushCurl, uBrushContrast;\n"
        "uniform float uBrushGlow, uBrushHaze;\n\nfloat hash21(vec2 p)", 1)
    helper = r"""
// Value noise with an analytic spatial gradient: curl is tangent to the
// smooth contour sheets, rather than a constant diagonal brush direction.
vec3 currentNoise(vec2 p) {
    vec2 i=floor(p), f=fract(p);
    vec2 s=f*f*(3.-2.*f), ds=6.*f*(1.-f);
    float a=hash21(i), b=hash21(i+vec2(1,0));
    float c=hash21(i+vec2(0,1)), d=hash21(i+vec2(1,1));
    return vec3(mix(mix(a,b,s.x),mix(c,d,s.x),s.y),
                ds.x*mix(b-a,d-c,s.y),ds.y*mix(c-a,d-b,s.x));
}
vec3 currentPotential(vec2 p, float t, float seed) {
    float scale=uBrushScale;
    vec2 offset=vec2(seed*.37,seed*.71)+t*vec2(.045,-.037);
    vec3 a=currentNoise(p*scale+offset);
    vec3 b=currentNoise(rot(.67)*p*scale*1.87+offset*.73+13.7);
    vec2 grad=.76*a.yz*scale+.24*(transpose(rot(.67))*b.yz)*scale*1.87;
    return vec3(.76*a.x+.24*b.x,grad);
}
vec2 currentVelocity(vec2 p, float t, float seed) {
    vec3 n=currentPotential(p,t,seed);
    vec2 tangent=vec2(-n.z,n.y);
    float level=mix(.72,.32,uCoverage);
    // Converging, curling currents: wisps emerge from the dark cavities and
    // gather along the luminous sheets, instead of tracing uniform rings.
    vec2 current=tangent*(.15+uBrushCurl*.55)+n.yz*tanh((level-n.x)*12.)*1.4;
    vec2 drift=vec2(cos(radians(uDirection)),sin(radians(uDirection)));
    vec2 v=mix(drift,current,uParticleFlow);
    return v/max(length(v),.08);
}
vec2 currentCoordinates(vec2 p, float t, float seed) {
    vec2 direction=vec2(cos(radians(uDirection)),sin(radians(uDirection)));
    vec2 moving=p-direction*t*uDrift*.15;
    moving+=uWander*.18*vec2(sin(t*.53+seed),cos(t*.39+seed));
    vec2 q=flow(moving,t,seed);
    return q+uBrushCurl*.18*vec2(sin(q.y*3.+t*.23),cos(q.x*3.-t*.19));
}
float softCurrent(vec2 p, float t, float seed) {
    float value=currentPotential(p,t,seed).x;
    float level=mix(.72,.32,uCoverage);
    float width=uBrushWidth*(.35+uBleed*.8);
    float ribbon=exp(-pow((value-level)/max(width,.004),2.));
    return pow(ribbon,uBrushContrast)*step(.0001,uCoverage);
}
float currentWisps(vec2 p, float t, float seed) {
    if(uParticleDensity<=0.) return 0.;
    vec2 q=p+uParticleJitter*.025*vec2(sin(p.y*17.+t),cos(p.x*13.-t*.7));
    float stepSize=.0012*(.35+uParticleTrail*(1.+uBrushLength*2.5));
    float frequency=260./max(uParticleSize,.3);
    float threshold=mix(.87,.12,uParticleDensity), total=0., weight=0.;
    // Symmetric bounded trails avoid feedback history and time-seek jumps.
    for(int side=0;side<2;side++) {
        vec2 point=q;
        for(int i=0;i<12;i++) {
            float w=1.-float(i)/13.;
            float sampleNoise=noise2(point*frequency+seed+t*vec2(.7,-.5));
            float particle=smoothstep(threshold,threshold+.08+.25*uParticleSoftness,sampleNoise);
            total+=particle*w; weight+=w;
            vec2 v=currentVelocity(point,t,seed);
            point+=(side==0 ? -1. : 1.)*v*stepSize;
        }
    }
    float strands=smoothstep(.08,.82,total/max(weight,.001));
    // Softness lowers strand contrast as well as smoothing each seed grain;
    // this keeps the default luminous/smoky rather than an etched ink texture.
    float fine=pow(strands,1.+uBrushContrast*.4)*.85;
    return mix(fine,.2+.55*fine,uParticleSoftness*.6);
}
"""
    shader = shader.replace("void main() {", helper+"\nvoid main() {", 1)
    shader = shader.replace("vec2 q=flow(moving,t,seed);\n    float n=", """vec2 q=flow(moving,t,seed);
    if(uBrushEnabled>.5) q=currentCoordinates(p,t,seed);
    float n=""", 1)
    shader = shader.replace("float signal=mix(n,.48*n+.52*bands,uMarbling);", """float signal=mix(n,.48*n+.52*bands,uMarbling);
    if(uBrushEnabled>.5) signal=mix(signal,.2+.8*softCurrent(q,t,seed),uBrushWeb);""", 1)
    shader = shader.replace("float pool=", """if(uBrushEnabled>.5) {
        float ribbon=softCurrent(q,t,seed)*envelope;
        wet=mix(wet,pow(ribbon,1.5)*(.65+.35*bands*uMarbling),uBrushWeb);
        wash=mix(wash,pow(ribbon,.6)*envelope,uBrushWeb);
    }
    float pool=""", 1)
    shader = shader.replace("float dots=grains(pq,pt,seed);", """if(uBrushEnabled>.5) pq=mix(p,currentCoordinates(p,pt,seed),uParticleFlow);
        float dots=grains(pq,pt,seed);
        if(uBrushEnabled>.5) {
            float wisps=currentWisps(pq,pt,seed);
            dots=mix(dots,wisps,uBrushFibers);
            float current=softCurrent(pq,pt,seed)*envelope;
            particleMask=mix(particleMask,mix(pow(current,.5),envelope,uParticleSpread),uBrushWeb);
        }""", 1)
    shader = shader.replace("    if(uGlitterEnabled>.5", """    if(uBrushEnabled>.5 && uLiquidEnabled>.5) {
        // Premultiplied emission supplies the reference's bright soft cores;
        // alpha still comes from the liquid and remains zero for empty layers.
        float core=pow(wet,3.)*uInkAmount*uInkColor.a*uBrushGlow*3.;
        float haze=pow(wash,1.8)*uWashAmount*uWashColor.a*uBrushHaze;
        result.rgb+=uInkColor.rgb*core+uWashColor.rgb*haze;
    }
    if(uGlitterEnabled>.5""", 1)
    return tuple(parameters), shader


def radial_variant():
    """Center-emitting, seamless ring currents inheriting the entire brush API.

    The periodic angular harmonics have no polar seam. Analytic gradients and
    a softened origin keep trails finite at the center. Positive radial speed
    moves contour phases outward, using the inherited liquid/particle clocks.
    Switching radial mode off (or amount to zero) retains the brush renderer.
    """
    parameters, shader = brush_variant()
    parameters = list(parameters)
    defaults = dict(Stretch=1., Scale=.85, Coverage=.57, Brushglow=.2,
                    Brushwidth=.2, Brushscale=3.2, Brushhaze=.75,
                    Papertexture=.35, Granulation=.16, Particleamount=.65,
                    Particlesize=.9, Particlesoftness=.65, Washamount=.3,
                    Inkcolor=[.82,.94,1.,1.], Washcolor=[.75,.32,.62,1.],
                    Particlecolor=[.9,.96,1.,1.], Papercolor=[1.,.43,.14,1.],
                    Glittercolor=[1.,.91,.67,1.], Staticglittercolor=[1.,.91,.75,1.])
    for definition in parameters:
        if definition["page"] == "Ink Brush Flow":
            definition["page"] = "Ink Radial Flow"
        if definition["name"] in defaults:
            definition["default"] = defaults[definition["name"]]
    parameters.extend((
        dict(name="Radialenabled", label="Center Radiation Enabled", page="Radial Flow",
             type="toggle", default=True, uniform="uRadialEnabled"),
        _control("Radialamount", "Radial / Brush Blend", "Radial Flow", 1., uniform="uRadialAmount"),
        _control("Radialrings", "Radiating Ring Frequency", "Radial Flow", 4.2, 1., 24., uniform="uRadialRings"),
        _control("Radialspeed", "Outward Speed / Inward Reverse", "Radial Flow", .45, -3., 3., uniform="uRadialSpeed"),
        _control("Radialspiral", "Spiral Twist / Reverse", "Radial Flow", .7, -3., 3., uniform="uRadialSpiral"),
        _control("Radialwarp", "Organic Ring Wandering", "Radial Flow", 1., 0., 1.5, uniform="uRadialWarp"),
        _control("Radialcore", "Central Opening Radius", "Radial Light", .32, .05, 1.5, uniform="uRadialCore"),
        _control("Radialglow", "Central Light Amount", "Radial Light", .5, 0., 2., uniform="uRadialGlow"),
        _control("Radialatmosphere", "Palette Atmosphere", "Radial Light", .75, uniform="uRadialAtmosphere"),
        _control("Radialfalloff", "Outer Ring Fade", "Radial Light", .2, uniform="uRadialFalloff"),
    ))

    def replace_once(old, new):
        nonlocal shader
        if shader.count(old) != 1:
            raise ValueError("Radial shader anchor changed: " + old[:60])
        shader = shader.replace(old, new, 1)

    replace_once("float hash21(vec2 p)", """uniform float uRadialEnabled, uRadialAmount, uRadialRings, uRadialSpeed;
uniform float uRadialSpiral, uRadialWarp, uRadialCore, uRadialGlow;
uniform float uRadialAtmosphere, uRadialFalloff;
float hash21(vec2 p)""")
    replace_once("vec3 currentPotential(vec2 p, float t, float seed) {", r"""
float radialBlend() { return uRadialEnabled>.5 ? uRadialAmount : 0.; }
vec3 radialPotential(vec2 p, float t, float seed) {
    float r=max(length(p),.001), core=max(uRadialCore,.05);
    vec2 outward=p/r;
    // Integer angular harmonics join exactly across -pi / +pi. Damping at
    // the origin removes the angular singularity without a center pinhole.
    float a=atan(p.y,p.x+.000001);
    vec2 angular=vec2(-p.y,p.x)/max(dot(p,p),.000001);
    float damp=1.-exp(-dot(p,p)/(core*core));
    vec2 dampGradient=2.*p/(core*core)*(1.-damp);
    float first=3.*a+r*uRadialSpiral*6.+seed+t*.14;
    float second=5.*a-r*uRadialSpiral*3.-seed*.7-t*.11;
    float wander=sin(first)+.45*sin(second);
    vec2 wanderGradient=cos(first)*(3.*angular+outward*uRadialSpiral*6.)
                      +.45*cos(second)*(5.*angular-outward*uRadialSpiral*3.);
    vec3 detail=currentNoise(p*uBrushScale+seed+t*vec2(.02,-.015));
    // Log-radius gives fine waves at the opening and broad flowing sheets at
    // the outside, avoiding a uniform radar/bullseye pattern.
    float frequency=uRadialRings*3.;
    float phase=log(1.+r/core)*frequency-t*uRadialSpeed*6.2831853
               +uRadialWarp*1.5*(damp*wander+.35*(detail.x-.5));
    vec2 gradient=outward*frequency/(core+r)+uRadialWarp*1.5*
                 (damp*wanderGradient+dampGradient*wander+.35*detail.yz*uBrushScale);
    return vec3(.5+.25*sin(phase),.25*cos(phase)*gradient);
}
vec3 currentPotential(vec2 p, float t, float seed) {""")
    replace_once("return vec3(.76*a.x+.24*b.x,grad);",
                 "return mix(vec3(.76*a.x+.24*b.x,grad),radialPotential(p,t,seed),radialBlend());")
    replace_once("vec2 v=mix(drift,current,uParticleFlow);", """vec2 outward=p/max(length(p),.03);
    vec2 radiation=outward*(uRadialSpeed>=0. ? 1. : -1.)
                  +vec2(-outward.y,outward.x)*uRadialSpiral*.8;
    current=mix(current,radiation+current*.18,radialBlend());
    vec2 v=mix(drift,current,uParticleFlow);""")
    replace_once("return q+uBrushCurl*.18*vec2(sin(q.y*3.+t*.23),cos(q.x*3.-t*.19));", """vec2 brush=q+uBrushCurl*.18*vec2(sin(q.y*3.+t*.23),cos(q.x*3.-t*.19));
    float r=length(p), anchor=1.-exp(-r*r/.04);
    vec2 softWarp=vec2(fbm(p*2.3+seed+t*.11),fbm(p*2.3-seed-t*.09+31.7))-.5;
    vec2 radial=p+softWarp*anchor*uTurbulence*uFlowAmount*uRadialWarp*.4;
    radial=rot(uSwirl*uFlowAmount*uBrushCurl*.2*anchor*sin(t*.27+seed))*radial;
    radial+=anchor*(uWander*.025*vec2(sin(t*.53+seed),cos(t*.39+seed))
                   -direction*t*uDrift*.025);
    return mix(brush,radial,radialBlend());""")
    replace_once("float envelope=exp(-dot(p*vec2(.72,1.),p*vec2(.72,1.))/(uSpread*uSpread*3.));", """float envelope=exp(-dot(p*vec2(.72,1.),p*vec2(.72,1.))/(uSpread*uSpread*3.));
    envelope*=mix(1.,exp(-length(p)*.85/max(uSpread,.1)),radialBlend()*uRadialFalloff);""")
    replace_once("vec4 result=vec4(paper*uPaperColor.a,uPaperColor.a);", """float atmosphere=radialBlend()*uRadialAtmosphere;
    float vertical=smoothstep(-1.2,1.2,p.y);
    vec3 ambient=mix(uPaperColor.rgb,uWashColor.rgb,vertical*.65);
    ambient=mix(ambient,uInkColor.rgb,vertical*vertical*.8);
    float opening=exp(-dot(p,p)/max(uRadialCore*uRadialCore*8.,.001));
    ambient=mix(ambient,uInkColor.rgb,opening*.82);
    paper=mix(paper,ambient*paperTone*(1.-uVignette*rim*.3),atmosphere);
    vec4 result=vec4(paper*uPaperColor.a,uPaperColor.a);""")
    replace_once("    if(uGlitterEnabled>.5", """    if(uLiquidEnabled>.5 && radialBlend()>0. && uRadialGlow>0.) {
        float core=exp(-dot(p,p)/max(uRadialCore*uRadialCore,.001));
        vec4 light=vec4(uInkColor.rgb*(1.+uRadialGlow),uInkColor.a);
        result=overInk(result,light,core*uRadialGlow*uInkAmount*radialBlend());
    }
    if(uGlitterEnabled>.5""")
    return tuple(parameters), shader


def pack_scalar_uniforms(shader, definitions):
    """Pack scalar controls into vec4 slots without limiting the control count.

    TouchDesigner vector sequence rows are finite. Color/XY uniforms retain
    their dedicated rows; macros preserve the readable shader's scalar names.
    Returned bindings contain only trusted parameter-name expressions.
    """
    import re
    scalar = [d for d in definitions if d.get("uniform") and d["type"] not in ("xy", "rgb", "rgba")]
    shader = re.sub(r"uniform\s+float\s+[^;]+;", "", shader)
    preamble, bindings = [], []
    for index in range(0, len(scalar), 4):
        name = "uPacked" + str(index // 4)
        preamble.append("uniform vec4 " + name + ";")
        values = []
        for axis, definition in zip("xyzw", scalar[index:index+4]):
            preamble.append("#define " + definition["uniform"] + " " + name + "." + axis)
            values.append("parent().par." + definition["name"] + (".menuIndex" if definition["type"] == "menu" else ""))
        bindings.append((name, values))
    return "\n".join(preamble) + "\n" + shader, bindings
