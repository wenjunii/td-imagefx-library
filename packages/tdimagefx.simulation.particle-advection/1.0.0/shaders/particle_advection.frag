uniform float uMix; uniform float uSpeed; uniform float uDecay; uniform float uThreshold; uniform float uPhase;
layout(location = 0) out vec4 fragColor;
void main() {
    vec2 uv=vUV.st; vec4 src=texture(sTD2DInputs[0],uv); float angle=sin(uv.x*19.0+uPhase)*3.0+cos(uv.y*17.0-uPhase)*2.0;
    vec2 flow=vec2(cos(angle),sin(angle))*uSpeed; vec3 old=texture(sTD2DInputs[1],uv-flow).rgb*uDecay;
    float seed=smoothstep(uThreshold,1.0,max(src.r,max(src.g,src.b))); vec3 particles=max(old,src.rgb*seed);
    fragColor=TDOutputSwizzle(vec4(mix(src.rgb,particles,clamp(uMix,0.0,1.0)),src.a));
}
