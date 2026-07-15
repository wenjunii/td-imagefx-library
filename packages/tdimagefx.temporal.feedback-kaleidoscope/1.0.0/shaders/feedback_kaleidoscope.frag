uniform float uMix; uniform float uSegments; uniform float uZoom; uniform float uFeedback;
layout(location = 0) out vec4 fragColor;
void main() {
    vec2 uv = vUV.st; vec2 p = uv - .5; float r = length(p) / max(uZoom, .001); float a = atan(p.y, p.x);
    float wedge = 6.28318530718 / max(2.0, floor(uSegments)); a = abs(mod(a, wedge) - .5 * wedge);
    vec2 q = .5 + r * vec2(cos(a), sin(a)); vec4 src = texture(sTD2DInputs[0], uv);
    vec3 effected = mix(src.rgb, texture(sTD2DInputs[1], q).rgb, uFeedback);
    fragColor = TDOutputSwizzle(vec4(mix(src.rgb, effected, clamp(uMix, 0.0, 1.0)), src.a));
}
