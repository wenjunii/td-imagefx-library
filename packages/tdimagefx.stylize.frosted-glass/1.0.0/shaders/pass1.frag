layout(location = 0) out vec4 fragColor;

uniform float uScale;
uniform float uDistortion;
uniform float uSeed;

float cellHash(vec2 cell, float seed)
{
    vec2 p = mod(cell + vec2(seed * 17.0, seed * 31.0), 289.0);
    float n = mod((p.x * 34.0 + 1.0) * p.x + p.y, 289.0);
    n = mod((n * 34.0 + 1.0) * n + p.x, 289.0);
    return fract(n / 41.0);
}

void main()
{
    vec2 uv = vUV.st;
    float scale = max(uScale, 1.0);
    vec2 cell = floor(uv * scale);
    vec2 jitter = vec2(
        cellHash(cell, uSeed),
        cellHash(cell.yx + vec2(13.0, 7.0), uSeed + 19.0)
    ) - 0.5;
    vec2 texel = 1.0 / max(uTD2DInfos[0].res.zw, vec2(1.0));
    vec2 displacedUv = clamp(uv + jitter * texel * max(uDistortion, 0.0), vec2(0.0), vec2(1.0));
    vec4 source = texture(sTD2DInputs[0], uv);
    vec3 refracted = texture(sTD2DInputs[0], displacedUv).rgb;
    fragColor = TDOutputSwizzle(vec4(refracted, source.a));
}
