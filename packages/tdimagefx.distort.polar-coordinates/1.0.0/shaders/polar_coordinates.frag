layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform float uRotation;
uniform float uRadiusScale;
uniform float uRepeats;
uniform float uCenterX;
uniform float uCenterY;

void main()
{
    vec2 uv = vUV.st;
    vec2 center = vec2(uCenterX, uCenterY);
    float aspect = uTD2DInfos[0].res.z / max(uTD2DInfos[0].res.w, 1.0);
    vec2 p = uv - center;
    p.x *= aspect;

    float angle = atan(p.y, p.x) / 6.28318530718 + 0.5;
    float angularCoordinate = fract(angle * max(uRepeats, 1.0) + uRotation);
    float radialCoordinate = clamp(length(p) * max(uRadiusScale, 0.001), 0.0, 1.0);
    vec2 polarUV = vec2(angularCoordinate, radialCoordinate);

    vec4 source = texture(sTD2DInputs[0], uv);
    vec4 effect = texture(sTD2DInputs[0], polarUV);
    fragColor = TDOutputSwizzle(mix(source, effect, clamp(uMix, 0.0, 1.0)));
}
