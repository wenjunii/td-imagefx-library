// Stateful pass. Input 0 is source; input 1 is the previous wet state.
uniform float uFeedback;
uniform float uOffsetX;
uniform float uOffsetY;
uniform vec4 uTint;

layout(location = 0) out vec4 fragColor;

void main() {
    vec2 uv = vUV.st;
    vec4 src = texture(sTD2DInputs[0], uv);
    vec3 prior = texture(sTD2DInputs[1], uv - vec2(uOffsetX, uOffsetY)).rgb;
    vec3 wet = src.rgb + prior * uTint.rgb * clamp(uFeedback, 0.0, 0.98);
    fragColor = TDOutputSwizzle(vec4(wet, src.a));
}
