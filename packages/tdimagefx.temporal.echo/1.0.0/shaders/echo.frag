uniform float uMix; uniform float uFeedback; uniform float uOffsetX; uniform float uOffsetY; uniform vec4 uTint;
layout(location = 0) out vec4 fragColor;
void main() {
    vec2 uv = vUV.st; vec4 src = texture(sTD2DInputs[0], uv);
    vec3 echoColor = texture(sTD2DInputs[1], uv - vec2(uOffsetX, uOffsetY)).rgb * uTint.rgb;
    vec3 effected = src.rgb + echoColor * uFeedback;
    fragColor = TDOutputSwizzle(vec4(mix(src.rgb, effected, clamp(uMix, 0.0, 1.0)), src.a));
}
