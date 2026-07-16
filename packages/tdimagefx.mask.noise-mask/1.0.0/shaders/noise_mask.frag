uniform float uMix;
uniform float uScale;
uniform float uThreshold;
uniform float uSoftness;
uniform float uSeed;
uniform float uTime;
uniform float uSpeed;
uniform float uInvert;

layout(location = 0) out vec4 fragColor;

float hash21(vec2 point)
{
    point = fract(point * vec2(123.34, 456.21));
    point += dot(point, point + 45.32 + uSeed * 0.001);
    return fract(point.x * point.y);
}

float valueNoise(vec2 point)
{
    vec2 cell = floor(point);
    vec2 fraction = fract(point);
    fraction = fraction * fraction * (3.0 - 2.0 * fraction);
    return mix(mix(hash21(cell), hash21(cell + vec2(1.0, 0.0)), fraction.x),
               mix(hash21(cell + vec2(0.0, 1.0)), hash21(cell + vec2(1.0, 1.0)), fraction.x), fraction.y);
}

void main()
{
    vec2 uv = vUV.st;
    vec4 source = texture(sTD2DInputs[0], uv);
    vec2 point = uv * uScale + vec2(uTime * uSpeed, -uTime * uSpeed * 0.71);
    float noiseValue = valueNoise(point) * 0.5714;
    noiseValue += valueNoise(point * 2.03 + 17.0) * 0.2857;
    noiseValue += valueNoise(point * 4.07 - 9.0) * 0.1429;
    float matte = smoothstep(uThreshold - uSoftness, uThreshold + uSoftness, noiseValue);
    matte = mix(matte, 1.0 - matte, step(0.5, uInvert));
    vec4 masked = vec4(source.rgb, source.a * matte);
    fragColor = TDOutputSwizzle(mix(source, masked, clamp(uMix, 0.0, 1.0)));
}
