layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform float uStrength;
uniform float uRadius;
uniform float uCenterX;
uniform float uCenterY;

void main()
{
    vec2 uv = vUV.st;
    vec2 center = vec2(uCenterX, uCenterY);
    float aspect = uTD2DInfos[0].res.z / max(uTD2DInfos[0].res.w, 1.0);
    vec2 p = uv - center;
    p.x *= aspect;

    float radius = max(uRadius, 0.0001);
    float normalizedRadius = length(p) / radius;
    float falloff = 1.0 - smoothstep(0.0, 1.0, normalizedRadius);
    vec2 sampleOffset = p * (1.0 - clamp(uStrength, -1.0, 1.0) * falloff * 0.75);
    sampleOffset.x /= aspect;
    vec2 sampleUV = clamp(center + sampleOffset, vec2(0.0), vec2(1.0));

    vec4 source = texture(sTD2DInputs[0], uv);
    vec4 effect = texture(sTD2DInputs[0], sampleUV);
    fragColor = TDOutputSwizzle(mix(source, effect, clamp(uMix, 0.0, 1.0)));
}
