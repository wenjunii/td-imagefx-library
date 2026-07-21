uniform float uMix;
uniform float uRadius;
uniform float uThreshold;

layout(location = 0) out vec4 fragColor;

void main()
{
    vec2 uv = vUV.st;
    vec4 source = texture(sTD2DInputs[0], uv);
    vec2 texel = 1.0 / vec2(textureSize(sTD2DInputs[0], 0));
    vec3 accumulated = vec3(0.0);
    float weight = 0.0;
    const vec2 directions[8] = vec2[8](
        vec2(1.0, 0.0), vec2(-1.0, 0.0), vec2(0.0, 1.0), vec2(0.0, -1.0),
        vec2(0.7071, 0.7071), vec2(-0.7071, 0.7071), vec2(0.7071, -0.7071), vec2(-0.7071, -0.7071)
    );
    for (int distanceIndex = 1; distanceIndex <= 8; ++distanceIndex) {
        if (float(distanceIndex) > uRadius + 0.001) break;
        for (int directionIndex = 0; directionIndex < 8; ++directionIndex) {
            vec4 neighbor = texture(sTD2DInputs[0], uv + directions[directionIndex] * texel * float(distanceIndex));
            float contribution = neighbor.a / float(distanceIndex);
            accumulated += neighbor.rgb * contribution;
            weight += contribution;
        }
    }
    vec3 extended = weight > 0.000001 ? accumulated / weight : source.rgb;
    float needsRepair = 1.0 - step(uThreshold, source.a);
    vec4 repaired = vec4(mix(source.rgb, extended, needsRepair), source.a);
    fragColor = TDOutputSwizzle(mix(source, repaired, clamp(uMix, 0.0, 1.0)));
}
