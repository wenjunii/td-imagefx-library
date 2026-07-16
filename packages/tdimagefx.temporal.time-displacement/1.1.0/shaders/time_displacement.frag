// Stateful pass. Input 0 is source; input 1 is the previous wet state.
uniform float uAmount;
uniform float uPhase;
uniform float uSoftness;

layout(location = 0) out vec4 fragColor;

void main() {
    vec2 uv = vUV.st;
    vec4 src = texture(sTD2DInputs[0], uv);
    vec3 prior = texture(sTD2DInputs[1], uv).rgb;
    float luma = dot(src.rgb, vec3(0.2126, 0.7152, 0.0722));
    float mask = smoothstep(uPhase - uSoftness, uPhase + uSoftness, fract(luma + uPhase));
    vec3 wet = mix(src.rgb, prior, mask * clamp(uAmount, 0.0, 1.0));
    fragColor = TDOutputSwizzle(vec4(wet, src.a));
}
