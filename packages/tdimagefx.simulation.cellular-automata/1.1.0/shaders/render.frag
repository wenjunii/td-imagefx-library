// Display-only pass. Input 0 is encoded automata state; input 1 is source.
uniform float uMix;

layout(location = 0) out vec4 fragColor;

void main() {
    vec2 uv = vUV.st;
    vec4 state = texture(sTD2DInputs[0], uv);
    vec4 src = texture(sTD2DInputs[1], uv);
    float alive = step(0.5, state.r);
    vec3 color = mix(vec3(0.015, 0.02, 0.04), vec3(0.2, 0.9, 1.0), alive);
    color += state.g * vec3(0.03, 0.12, 0.18);
    fragColor = TDOutputSwizzle(vec4(mix(src.rgb, color, clamp(uMix, 0.0, 1.0)), src.a));
}
