uniform float uMix; uniform float uDistance; uniform float uAngle; uniform float uFeedback;
layout(location = 0) out vec4 fragColor;
void main() {
    vec2 uv = vUV.st; vec2 d = vec2(cos(uAngle), sin(uAngle)) * uDistance; vec4 src = texture(sTD2DInputs[0], uv);
    vec3 acc = vec3(0.0); float weight = 0.0;
    for (int i = 0; i < 7; ++i) { float t = float(i) / 6.0; float w = 1.0 - t * .7; acc += texture(sTD2DInputs[1], uv - d * t).rgb * w; weight += w; }
    vec3 effected = mix(src.rgb, acc / weight, uFeedback);
    fragColor = TDOutputSwizzle(vec4(mix(src.rgb, effected, clamp(uMix, 0.0, 1.0)), src.a));
}
