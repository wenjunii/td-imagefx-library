uniform float uMix;
uniform vec2 uCenter;
uniform vec2 uSize;
uniform float uRoundness;
uniform float uRotation;
uniform float uFeather;
uniform float uInvert;

layout(location = 0) out vec4 fragColor;

float roundedBoxDistance(vec2 point, vec2 halfSize, float radius)
{
    vec2 q = abs(point) - max(halfSize - radius, vec2(0.0));
    return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - radius;
}

void main()
{
    vec2 uv = vUV.st;
    vec4 source = texture(sTD2DInputs[0], uv);
    float c = cos(-uRotation);
    float s = sin(-uRotation);
    vec2 point = mat2(c, -s, s, c) * (uv - uCenter);
    vec2 halfSize = max(abs(uSize) * 0.5, vec2(0.000001));
    float radius = min(halfSize.x, halfSize.y) * clamp(uRoundness, 0.0, 1.0);
    float distanceToShape = roundedBoxDistance(point, halfSize, radius);
    float matte = 1.0 - smoothstep(-uFeather, uFeather, distanceToShape);
    matte = mix(matte, 1.0 - matte, step(0.5, uInvert));
    vec4 masked = vec4(source.rgb, source.a * matte);
    fragColor = TDOutputSwizzle(mix(source, masked, clamp(uMix, 0.0, 1.0)));
}
