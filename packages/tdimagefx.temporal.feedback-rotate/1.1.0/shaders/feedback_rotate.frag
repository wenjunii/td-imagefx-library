// Stateful pass. Input 0 is source; input 1 is the previous wet state.
uniform float uAngle;
uniform float uScale;
uniform float uFeedback;

layout(location = 0) out vec4 fragColor;

void main() {
    vec2 uv = vUV.st;
    vec2 p = uv - 0.5;
    float c = cos(uAngle);
    float s = sin(uAngle);
    vec2 historyUv = mat2(c, -s, s, c) * p / max(uScale, 0.001) + 0.5;
    vec4 src = texture(sTD2DInputs[0], uv);
    vec3 prior = texture(sTD2DInputs[1], historyUv).rgb;
    vec3 wet = mix(src.rgb, prior, clamp(uFeedback, 0.0, 0.995));
    fragColor = TDOutputSwizzle(vec4(wet, src.a));
}
