layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform float uTime;
uniform float uAmount;
uniform float uPixelSize;
uniform float uRate;
uniform float uMonochrome;
uniform float uSeed;

float pixelHash(vec2 cell, float frame, float salt)
{
    float value = mod(cell.x * 181.0 + cell.y * 271.0 + frame * 101.0 + uSeed * 47.0 + salt * 67.0 + 13.0, 4099.0);
    return mod((value + 31.0) * (value * 59.0 + 23.0), 65537.0) / 65537.0;
}

void main()
{
    vec2 uv = vUV.st;
    vec2 resolution = uTD2DInfos[0].res.zw;
    vec2 cell = floor(uv * resolution / max(uPixelSize, 1.0));
    float frame = floor(uTime * max(uRate, 0.0));
    vec3 noiseRGB = vec3(
        pixelHash(cell, frame, 0.0),
        pixelHash(cell, frame, 1.0),
        pixelHash(cell, frame, 2.0)
    );
    noiseRGB = mix(noiseRGB, vec3(noiseRGB.r), step(0.5, uMonochrome));

    vec4 source = texture(sTD2DInputs[0], uv);
    vec3 noisyRGB = clamp(source.rgb + (noiseRGB - 0.5) * uAmount, vec3(0.0), vec3(1.0));
    vec4 effect = vec4(noisyRGB, source.a);
    fragColor = TDOutputSwizzle(mix(source, effect, clamp(uMix, 0.0, 1.0)));
}
