// Stateful pass. Input 0 is source; input 1 is the previous wet state.
uniform float uDistance;
uniform float uAngle;
uniform float uFeedback;

layout(location = 0) out vec4 fragColor;

void main() {
    vec2 uv = vUV.st;
    vec2 direction = vec2(cos(uAngle), sin(uAngle)) * uDistance;
    vec4 src = texture(sTD2DInputs[0], uv);
    vec3 accumulation = vec3(0.0);
    float weight = 0.0;
    for (int i = 0; i < 7; ++i) {
        float t = float(i) / 6.0;
        float sampleWeight = 1.0 - t * 0.7;
        accumulation += texture(sTD2DInputs[1], uv - direction * t).rgb * sampleWeight;
        weight += sampleWeight;
    }
    vec3 priorSmear = accumulation / max(weight, 0.0001);
    vec3 wet = mix(src.rgb, priorSmear, clamp(uFeedback, 0.0, 1.0));
    fragColor = TDOutputSwizzle(vec4(wet, src.a));
}
