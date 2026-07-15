uniform float uMix; uniform float uAngle; uniform float uScale; uniform float uFeedback;
layout(location = 0) out vec4 fragColor;
void main() {
    vec2 uv = vUV.st; vec2 p = uv - .5; float c = cos(uAngle), s = sin(uAngle);
    vec2 q = mat2(c, -s, s, c) * p / max(uScale, .001) + .5; vec4 src = texture(sTD2DInputs[0], uv);
    vec3 effected = mix(src.rgb, texture(sTD2DInputs[1], q).rgb, uFeedback);
    fragColor = TDOutputSwizzle(vec4(mix(src.rgb, effected, clamp(uMix, 0.0, 1.0)), src.a));
}
