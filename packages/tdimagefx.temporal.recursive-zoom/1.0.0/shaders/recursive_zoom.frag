uniform float uMix; uniform float uZoom; uniform float uFeedback; uniform float uCenterX; uniform float uCenterY;
layout(location = 0) out vec4 fragColor;
void main() {
    vec2 uv = vUV.st; vec2 center = vec2(uCenterX, uCenterY); vec4 src = texture(sTD2DInputs[0], uv);
    vec2 historyUv = center + (uv - center) / max(uZoom, .001); vec3 old = texture(sTD2DInputs[1], historyUv).rgb;
    vec3 effected = mix(src.rgb, old, uFeedback);
    fragColor = TDOutputSwizzle(vec4(mix(src.rgb, effected, clamp(uMix, 0.0, 1.0)), src.a));
}
