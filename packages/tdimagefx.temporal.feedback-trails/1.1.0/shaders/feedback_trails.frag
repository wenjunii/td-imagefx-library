// Stateful pass. Input 0 is source; input 1 is the previous wet state.
uniform float uFeedback;
uniform float uDecay;
uniform float uOffsetX;
uniform float uOffsetY;

layout(location = 0) out vec4 fragColor;

void main() {
    vec2 uv = vUV.st;
    vec4 src = texture(sTD2DInputs[0], uv);
    vec3 prior = texture(sTD2DInputs[1], uv - vec2(uOffsetX, uOffsetY)).rgb;
    float feedback = clamp(uFeedback, 0.0, 0.995);
    vec3 wet = max(src.rgb, prior * clamp(uDecay, 0.0, 1.0) * feedback + src.rgb * (1.0 - feedback));
    fragColor = TDOutputSwizzle(vec4(wet, src.a));
}
