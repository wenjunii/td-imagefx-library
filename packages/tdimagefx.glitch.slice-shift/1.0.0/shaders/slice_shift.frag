layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform float uTime;
uniform float uAmount;
uniform float uSlices;
uniform float uSpeed;
uniform float uStagger;
uniform float uSeed;

float sliceHash(float slice)
{
    float value = mod(slice * 193.0 + uSeed * 71.0 + 19.0, 4099.0);
    return mod((value + 37.0) * (value * 53.0 + 29.0), 65537.0) / 65537.0;
}

void main()
{
    vec2 uv = vUV.st;
    float slice = floor(uv.y * max(uSlices, 1.0));
    float direction = mix(-1.0, 1.0, mod(slice, 2.0));
    float phase = uTime * uSpeed + slice * uStagger + sliceHash(slice) * 6.28318530718;
    float offset = sin(phase) * uAmount * direction;
    vec2 shiftedUV = vec2(fract(uv.x + offset), uv.y);

    vec4 source = texture(sTD2DInputs[0], uv);
    vec4 effect = texture(sTD2DInputs[0], shiftedUV);
    fragColor = TDOutputSwizzle(mix(source, effect, clamp(uMix, 0.0, 1.0)));
}
