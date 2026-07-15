uniform float uMix; uniform float uFeedback; uniform float uDecay; uniform float uOffsetX; uniform float uOffsetY;
layout(location = 0) out vec4 fragColor;
void main() {
    vec2 uv = vUV.st; vec4 src = texture(sTD2DInputs[0], uv);
    vec3 old = texture(sTD2DInputs[1], uv - vec2(uOffsetX, uOffsetY)).rgb * uDecay;
    vec3 trails = max(src.rgb, old * uFeedback + src.rgb * (1.0 - uFeedback));
    fragColor = TDOutputSwizzle(vec4(mix(src.rgb, trails, clamp(uMix, 0.0, 1.0)), src.a));
}
