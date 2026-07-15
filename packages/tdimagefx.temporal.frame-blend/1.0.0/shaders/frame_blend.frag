uniform float uMix; uniform float uHistory;
layout(location = 0) out vec4 fragColor;
void main() {
    vec2 uv = vUV.st; vec4 src = texture(sTD2DInputs[0], uv); vec4 old = texture(sTD2DInputs[1], uv);
    vec3 blended = mix(src.rgb, old.rgb, clamp(uHistory, 0.0, .995));
    fragColor = TDOutputSwizzle(vec4(mix(src.rgb, blended, clamp(uMix, 0.0, 1.0)), src.a));
}
