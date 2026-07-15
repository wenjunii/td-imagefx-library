uniform float uMix; uniform float uAmount; uniform float uViewX; uniform float uViewY; uniform float uDepthCenter;
layout(location = 0) out vec4 fragColor;
void main() {
    vec2 uv = vUV.st; vec4 src = texture(sTD2DInputs[0], uv); float depth = texture(sTD2DInputs[1], uv).r - uDepthCenter;
    vec4 shifted = texture(sTD2DInputs[0], uv + vec2(uViewX,uViewY) * depth * uAmount);
    fragColor = TDOutputSwizzle(vec4(mix(src.rgb, shifted.rgb, clamp(uMix,0.0,1.0)), src.a));
}
