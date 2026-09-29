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
    if(uParticlesEnabled>.5 && uParticleAmount>0.) {
        // Particle clock is independent; zero freezes grains even while ink moves.
        float pt=uTime*uParticleSpeed;
        vec2 pq=mix(p,flow(p,pt,seed),uParticleFlow);
        float particleMask=mix(wash,envelope,uParticleSpread);
        float dots=grains(pq,pt,seed);
        result=overInk(result,uParticleColor,dots*particleMask*uParticleAmount);
    }
    // Public TOP contract uses straight alpha; transparent background is usable
    // with an Over TOP and never carries hidden paper RGB at alpha zero.
    result.rgb=result.a>1e-6 ? result.rgb/result.a : vec3(0.);
    fragColor=TDOutputSwizzle(mix(source,result,clamp(uMix,0.,1.)));
}
"""
