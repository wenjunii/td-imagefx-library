uniform float uMix; uniform float uAmount; uniform float uBiasX; uniform float uBiasY;
layout(location = 0) out vec4 fragColor;
void main() {
    vec2 uv = vUV.st; vec4 src = texture(sTD2DInputs[0], uv); vec2 flow = texture(sTD2DInputs[1], uv).rg * 2.0 - 1.0;
    vec4 warped = texture(sTD2DInputs[0], uv - (flow + vec2(uBiasX,uBiasY)) * uAmount);
    fragColor = TDOutputSwizzle(vec4(mix(src.rgb, warped.rgb, clamp(uMix,0.0,1.0)), src.a));
}
