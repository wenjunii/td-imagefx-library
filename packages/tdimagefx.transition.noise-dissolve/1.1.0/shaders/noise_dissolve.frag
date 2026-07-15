layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform float uProgress;
uniform float uSoftness;
uniform float uScale;
uniform float uSeed;

float cellHash(vec2 cell)
{
    float x = mod(cell.x + uSeed * 17.0, 1009.0);
    float y = mod(cell.y + uSeed * 29.0, 1013.0);
    float left = x * 421.0 + y * 613.0 + 37.0;
    float right = x * 73.0 + y * 193.0 + 17.0;
    return mod(left * right, 104729.0) / 104729.0;
}

float valueNoise(vec2 p)
{
    vec2 i = floor(p);
    vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    float a = cellHash(i + vec2(0.0, 0.0));
    float b = cellHash(i + vec2(1.0, 0.0));
    float c = cellHash(i + vec2(0.0, 1.0));
    float d = cellHash(i + vec2(1.0, 1.0));
    return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}

void main()
{
    vec2 uv = vUV.st;
    vec4 imageA = texture(sTD2DInputs[0], uv);
    vec4 imageB = texture(sTD2DInputs[1], uv);
    float noiseValue = valueNoise(uv * max(uScale, 1.0));
    float softness = max(uSoftness, 0.0001);
    float transition = smoothstep(uProgress - softness, uProgress + softness, noiseValue);
    vec4 effect = mix(imageB, imageA, transition);
    fragColor = TDOutputSwizzle(mix(imageA, effect, clamp(uMix, 0.0, 1.0)));
}
