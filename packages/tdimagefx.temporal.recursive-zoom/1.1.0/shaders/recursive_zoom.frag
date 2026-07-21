// Stateful pass. Input 0 is source; input 1 is the previous wet state.
uniform float uZoom;
uniform float uFeedback;
uniform float uCenterX;
uniform float uCenterY;

layout(location = 0) out vec4 fragColor;

void main() {
    vec2 uv = vUV.st;
    vec2 center = vec2(uCenterX, uCenterY);
    vec4 src = texture(sTD2DInputs[0], uv);
    vec2 historyUv = center + (uv - center) / max(uZoom, 0.001);
    vec3 prior = texture(sTD2DInputs[1], historyUv).rgb;
    vec3 wet = mix(src.rgb, prior, clamp(uFeedback, 0.0, 0.995));
    fragColor = TDOutputSwizzle(vec4(wet, src.a));
}
