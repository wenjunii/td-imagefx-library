layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform float uTime;
uniform float uJitter;
uniform float uJitterRate;
uniform float uChromaDelay;
uniform float uScanlineStrength;
uniform float uNoise;
uniform float uTracking;

float oscillatorNoise(vec2 pixel, float phase)
{
    float waveA = sin(pixel.x * 0.7548777 + pixel.y * 0.5698403 + phase);
    float waveB = cos(pixel.x * 0.4382890 + pixel.y * 1.1370000 + phase * 1.73);
    return fract((waveA + waveB) * 91.3458);
}

void main()
{
    vec2 uv = vUV.st;
    vec2 resolution = max(uTD2DInfos[0].res.zw, vec2(1.0));
    vec4 source = texture(sTD2DInputs[0], uv);
    float steppedTime = floor(uTime * max(uJitterRate, 0.0));
    float band = floor(uv.y * resolution.y / 4.0);
    float lineJitter = sin(band * 1.731 + steppedTime * 2.417) * uJitter;
    float trackingCenter = fract(uTime * 0.13);
    float trackingBand = exp(-pow((uv.y - trackingCenter) / 0.035, 2.0));
    vec2 distortedUV = uv + vec2(lineJitter + trackingBand * uTracking, 0.0);
    float chromaUV = uChromaDelay / resolution.x;
    float red = texture(sTD2DInputs[0], distortedUV + vec2(chromaUV, 0.0)).r;
    float green = texture(sTD2DInputs[0], distortedUV).g;
    float blue = texture(sTD2DInputs[0], distortedUV - vec2(chromaUV, 0.0)).b;
    vec3 tapeColor = vec3(red, green, blue);
    float scanline = 1.0 - clamp(uScanlineStrength, 0.0, 1.0) * (0.5 + 0.5 * sin(uv.y * resolution.y * 3.14159265));
    float noiseValue = oscillatorNoise(floor(uv * resolution), uTime * 37.0) - 0.5;
    tapeColor = tapeColor * scanline + vec3(noiseValue * uNoise + trackingBand * uNoise * 0.5);
    vec4 effect = vec4(tapeColor, source.a);
    fragColor = TDOutputSwizzle(mix(source, effect, clamp(uMix, 0.0, 1.0)));
}
