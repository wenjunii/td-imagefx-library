// Stateful pass. Input 0 is source; input 1 is the previous wet state.
uniform float uHold;

layout(location = 0) out vec4 fragColor;

void main() {
    vec2 uv = vUV.st;
    vec4 src = texture(sTD2DInputs[0], uv);
    vec4 prior = texture(sTD2DInputs[1], uv);
    vec4 wet = mix(src, prior, step(0.5, uHold));
    fragColor = TDOutputSwizzle(vec4(wet.rgb, src.a));
}
