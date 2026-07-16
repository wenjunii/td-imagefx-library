// Stateful pass. Input 0 is source; input 1 is the previous wet state.
uniform float uHistory;

layout(location = 0) out vec4 fragColor;

void main() {
    vec2 uv = vUV.st;
    vec4 src = texture(sTD2DInputs[0], uv);
    vec3 prior = texture(sTD2DInputs[1], uv).rgb;
    vec3 wet = mix(src.rgb, prior, clamp(uHistory, 0.0, 0.995));
    fragColor = TDOutputSwizzle(vec4(wet, src.a));
}
