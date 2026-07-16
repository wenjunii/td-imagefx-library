// Stateful pass. Input 0 is source; input 1 is the previous wet state.
uniform float uSegments;
uniform float uZoom;
uniform float uFeedback;

layout(location = 0) out vec4 fragColor;

void main() {
    vec2 uv = vUV.st;
    vec2 p = uv - 0.5;
    float radius = length(p) / max(uZoom, 0.001);
    float angle = atan(p.y, p.x);
    float wedge = 6.28318530718 / max(2.0, floor(uSegments));
    angle = abs(mod(angle, wedge) - 0.5 * wedge);
    vec2 historyUv = 0.5 + radius * vec2(cos(angle), sin(angle));
    vec4 src = texture(sTD2DInputs[0], uv);
    vec3 prior = texture(sTD2DInputs[1], historyUv).rgb;
    vec3 wet = mix(src.rgb, prior, clamp(uFeedback, 0.0, 0.995));
    fragColor = TDOutputSwizzle(vec4(wet, src.a));
}
