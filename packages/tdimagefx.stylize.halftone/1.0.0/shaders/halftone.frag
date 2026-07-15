layout(location = 0) out vec4 fragColor;

uniform float uMix;
uniform float uCellSize;
uniform float uAngle;
uniform float uDotSize;
uniform float uSoftness;
uniform float uMonochrome;

mat2 rotateGrid(float angle)
{
    float sineValue = sin(angle);
    float cosineValue = cos(angle);
    return mat2(cosineValue, -sineValue, sineValue, cosineValue);
}

void main()
{
    vec2 uv = vUV.st;
    vec4 source = texture(sTD2DInputs[0], uv);
    vec2 resolution = uTD2DInfos[0].res.zw;
    float cellSize = max(uCellSize, 1.0);
    vec2 grid = rotateGrid(uAngle) * ((uv - 0.5) * resolution) / cellSize;
    vec2 local = fract(grid) - 0.5;
    float luma = clamp(dot(source.rgb, vec3(0.2126, 0.7152, 0.0722)), 0.0, 1.0);
    float radius = sqrt(max(1.0 - luma, 0.0)) * 0.68 * uDotSize;
    float coverage = 1.0 - smoothstep(radius, radius + max(uSoftness, 0.0001), length(local));
    vec3 monochrome = vec3(1.0 - coverage);
    vec3 colorPrint = vec3(1.0) - coverage * (vec3(1.0) - source.rgb);
    vec3 printed = mix(colorPrint, monochrome, clamp(uMonochrome, 0.0, 1.0));
    vec4 effect = vec4(printed, source.a);
    fragColor = TDOutputSwizzle(mix(source, effect, clamp(uMix, 0.0, 1.0)));
}
