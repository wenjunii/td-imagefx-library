uniform float uMix;
uniform vec2 uBottomLeft;
uniform vec2 uBottomRight;
uniform vec2 uTopLeft;
uniform vec2 uTopRight;

layout(location = 0) out vec4 fragColor;

void main()
{
    vec2 uv = vUV.st;
    vec4 source = texture(sTD2DInputs[0], uv);
    vec2 lower = mix(uBottomLeft, uBottomRight, uv.x);
    vec2 upper = mix(uTopLeft, uTopRight, uv.x);
    vec2 sampleUv = mix(lower, upper, uv.y);
    bool inside = all(greaterThanEqual(sampleUv, vec2(0.0))) && all(lessThanEqual(sampleUv, vec2(1.0)));
    vec4 pinned = inside ? texture(sTD2DInputs[0], sampleUv) : vec4(0.0);
    fragColor = TDOutputSwizzle(mix(source, pinned, clamp(uMix, 0.0, 1.0)));
}
