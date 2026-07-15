uniform float uMix; uniform float uAdvection; uniform float uDecay; uniform float uInjection; uniform float uPhase;

// Project-original cell hash. It avoids the commonly copied sine-hash expression.
float tdImageFxCellHash(vec2 p) {
    vec2 cell = mod(floor(p), vec2(251.0, 241.0));
    float mixed = cell.x * 73.0 + cell.y * 151.0 + cell.x * cell.y * 0.137;
    mixed = mod(mixed * mixed + mixed * 31.0 + 17.0, 65521.0);
    return fract(mixed / 65521.0 + mixed * 0.00000011920928955078125);
}
layout(location = 0) out vec4 fragColor;
void main() {
    vec2 uv=vUV.st; vec4 src=texture(sTD2DInputs[0],uv); vec2 cell=floor(uv*48.0);
    float phase=floor(uPhase*83.0); float a=tdImageFxCellHash(cell+phase), b=tdImageFxCellHash(cell.yx-phase); vec2 flow=normalize(vec2(a-.5,b-.5)+vec2(.0001));
    vec3 old=texture(sTD2DInputs[1],uv-flow*uAdvection).rgb*uDecay; float ink=dot(src.rgb,vec3(.2126,.7152,.0722))*uInjection;
    vec3 fluid=max(old,src.rgb*ink); fragColor=TDOutputSwizzle(vec4(mix(src.rgb,fluid,clamp(uMix,0.0,1.0)),src.a));
}
