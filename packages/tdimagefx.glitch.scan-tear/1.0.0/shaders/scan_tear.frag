layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform float uTime;
uniform float uAmount;
uniform float uBands;
uniform float uRate;
uniform float uChance;
uniform float uSeed;

float bandHash(float band, float frame, float salt)
{
    float value = mod(band * 173.0 + frame * 269.0 + uSeed * 97.0 + salt * 43.0 + 11.0, 4099.0);
    return mod((value + 29.0) * (value * 61.0 + 17.0), 65537.0) / 65537.0;
}

void main()
{
    vec2 uv = vUV.st;
    float band = floor(uv.y * max(uBands, 1.0));
    float frame = floor(uTime * max(uRate, 0.0));
    float gate = step(1.0 - clamp(uChance, 0.0, 1.0), bandHash(band, frame, 0.0));
    float offset = (bandHash(band, frame, 1.0) * 2.0 - 1.0) * uAmount * gate;
    vec2 tornUV = vec2(fract(uv.x + offset), uv.y);

    vec4 source = texture(sTD2DInputs[0], uv);
    vec4 effect = texture(sTD2DInputs[0], tornUV);
    fragColor = TDOutputSwizzle(mix(source, effect, clamp(uMix, 0.0, 1.0)));
}
