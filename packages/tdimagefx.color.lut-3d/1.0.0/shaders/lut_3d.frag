uniform float uMix;
uniform float uSize;
uniform float uDomainMin;
uniform float uDomainMax;

layout(location = 0) out vec4 fragColor;

vec3 sampleLutSlice(vec3 coordinate, float sliceIndex, float size)
{
    float stripWidth = size * size;
    vec2 lutUv = vec2(
        (sliceIndex * size + coordinate.r * (size - 1.0) + 0.5) / stripWidth,
        (coordinate.g * (size - 1.0) + 0.5) / size
    );
    return texture(sTD2DInputs[1], lutUv).rgb;
}

void main()
{
    vec2 uv = vUV.st;
    vec4 source = texture(sTD2DInputs[0], uv);
    float size = max(floor(uSize + 0.5), 2.0);
    vec3 coordinate = clamp((source.rgb - uDomainMin) / max(uDomainMax - uDomainMin, 0.000001), 0.0, 1.0);
    float blue = coordinate.b * (size - 1.0);
    float lowSlice = floor(blue);
    float highSlice = min(lowSlice + 1.0, size - 1.0);
    vec3 lowColor = sampleLutSlice(coordinate, lowSlice, size);
    vec3 highColor = sampleLutSlice(coordinate, highSlice, size);
    vec3 graded = mix(lowColor, highColor, fract(blue));
    fragColor = TDOutputSwizzle(vec4(mix(source.rgb, graded, clamp(uMix, 0.0, 1.0)), source.a));
}
